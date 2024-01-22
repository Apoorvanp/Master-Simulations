""" Contains a component that uses the UTSP to provide LoadProfileGenerator data. """

# clean

import datetime
import errno
import io
import itertools
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
import copy
import enum
import pandas as pd
from dataclasses_json import dataclass_json

from utspclient import client, datastructures, result_file_filters
from utspclient.helpers import lpg_helper
from utspclient.helpers.lpgpythonbindings import HouseCreationAndCalculationJob
from utspclient.datastructures import TimeSeriesRequest
from utspclient.client import calculate_multiple_requests
from utspclient.helpers.lpgdata import (
    ChargingStationSets,
    Households,
    HouseTypes,
    LoadTypes,
    TransportationDeviceSets,
    TravelRouteSets,
    EnergyIntensityType,
)
from utspclient.helpers.lpgpythonbindings import CalcOption, JsonReference

# Owned
from hisim import component as cp
from hisim import loadtypes as lt
from hisim import log, utils
from hisim.components.configuration import HouseholdWarmWaterDemandConfig, PhysicsConfig
from hisim.simulationparameters import SimulationParameters
from hisim.component import OpexCostDataClass
from hisim.sim_repository_singleton import SingletonSimRepository, SingletonDictKeyEnum


class LpgDataAcquisitionMode(enum.Enum):

    """Set LPG Data Acquisition Mode."""

    USE_PREDEFINED_PROFILE = "use_predefined_profile"
    USE_UTSP = "use_utsp"


@dataclass_json
@dataclass
class UtspLpgConnectorConfig(cp.ConfigBase):

    """Config class for UtspLpgConnector. Contains LPG parameters and UTSP connection parameters."""

    name: str
    data_acquisition_mode: LpgDataAcquisitionMode
    household: Union[JsonReference, List[JsonReference]]
    energy_intensity: EnergyIntensityType
    travel_route_set: JsonReference
    transportation_device_set: JsonReference
    charging_station_set: JsonReference
    consumption: float
    profile_with_washing_machine_and_dishwasher: bool
    predictive_control: bool
    predictive: bool
    result_dir_path: str
    cache_dir_path: Optional[str] = None
    guid: str = ""

    @classmethod
    def get_main_classname(cls):
        """Returns the full class name of the base class."""
        return UtspLpgConnector.get_full_classname()

    @classmethod
    def get_default_utsp_connector_config(cls) -> Any:
        """Creates a default configuration. Chooses default values for the LPG parameters."""

        config = UtspLpgConnectorConfig(
            name="UTSPConnector",
            data_acquisition_mode=LpgDataAcquisitionMode.USE_UTSP,
            household=Households.CHR01_Couple_both_at_Work,
            result_dir_path=utils.HISIMPATH["utsp_results"],
            energy_intensity=EnergyIntensityType.EnergySaving,
            travel_route_set=TravelRouteSets.Travel_Route_Set_for_10km_Commuting_Distance,
            transportation_device_set=TransportationDeviceSets.Bus_and_one_30_km_h_Car,
            charging_station_set=ChargingStationSets.Charging_At_Home_with_11_kW,
            consumption=0,
            profile_with_washing_machine_and_dishwasher=True,
            predictive_control=False,
            predictive=False,
            cache_dir_path=None,
            guid="",
        )
        return config


class UtspLpgConnector(cp.Component):

    """Component that provides data from the LoadProfileGenerator.

    This component provides the heating generated, the electricity and water consumed
    by the residents. Furthermore, transportation and device flexibility data is stored
    in separate files, configurable via the config object.
    The data is retrieved from the UTSP, which executes the LoadProfileGenerator to simulate
    the specified household.
    """

    # Inputs
    WW_MassInput = "Warm Water Mass Input"  # kg/s
    WW_TemperatureInput = "Warm Water Temperature Input"  # °C

    # Outputs
    WW_MassOutput = "Mass Output"  # kg/s
    WW_TemperatureOutput = "Temperature Output"  # °C
    EnergyDischarged = "Energy Discharged"  # W
    DemandSatisfied = "Demand Satisfied"  # 0 or 1

    NumberByResidents = "NumberByResidents"
    HeatingByResidents = "HeatingByResidents"
    HeatingByDevices = "HeatingByDevices"
    ElectricityOutput = "ElectricityOutput"
    WaterConsumption = "WaterConsumption"

    Electricity_Demand_Forecast_24h = "Electricity_Demand_Forecast_24h"

    # Similar components to connect to:
    # None
    @utils.measure_execution_time
    def __init__(
        self,
        my_simulation_parameters: SimulationParameters,
        config: UtspLpgConnectorConfig,
    ) -> None:
        """Initializes the component and retrieves the LPG data."""
        self.utsp_config = config
        super().__init__(
            name=self.utsp_config.name,
            my_simulation_parameters=my_simulation_parameters,
            my_config=config,
        )
        self.build()
        # dummy value as long as there is no way to consider multiple households in one house
        self.scaling_factor_according_to_number_of_apartments: float = 1.0

        # Inputs - Not Mandatory
        self.ww_mass_input_channel: cp.ComponentInput = self.add_input(
            self.component_name,
            self.WW_MassInput,
            lt.LoadTypes.WARM_WATER,
            lt.Units.KG_PER_SEC,
            False,
        )
        self.ww_temperature_input_channel: cp.ComponentInput = self.add_input(
            self.component_name,
            self.WW_TemperatureInput,
            lt.LoadTypes.WARM_WATER,
            lt.Units.CELSIUS,
            False,
        )

        self.number_of_residents_channel: cp.ComponentOutput = self.add_output(
            self.component_name,
            self.NumberByResidents,
            lt.LoadTypes.ANY,
            lt.Units.ANY,
            output_description=f"here a description for LPG UTSP {self.NumberByResidents} will follow.",
        )
        self.heating_by_residents_channel: cp.ComponentOutput = self.add_output(
            self.component_name,
            self.HeatingByResidents,
            lt.LoadTypes.HEATING,
            lt.Units.WATT,
            output_description=f"here a description for LPG UTSP {self.HeatingByResidents} will follow.",
        )
        self.heating_by_devices_channel: cp.ComponentOutput = self.add_output(
            self.component_name,
            self.HeatingByDevices,
            lt.LoadTypes.HEATING,
            lt.Units.WATT,
            output_description="Inner device heat gains, which heat the building (not intentionally)",
        )
        self.electricity_output_channel: cp.ComponentOutput = self.add_output(
            object_name=self.component_name,
            field_name=self.ElectricityOutput,
            load_type=lt.LoadTypes.ELECTRICITY,
            unit=lt.Units.WATT,
            postprocessing_flag=[
                lt.InandOutputType.ELECTRICITY_CONSUMPTION_UNCONTROLLED
            ],
            output_description=f"here a description for LPG UTSP {self.ElectricityOutput} will follow.",
        )

        self.water_consumption_channel: cp.ComponentOutput = self.add_output(
            self.component_name,
            self.WaterConsumption,
            lt.LoadTypes.WARM_WATER,
            lt.Units.LITER,
            output_description=f"here a description for LPG UTSP {self.WaterConsumption} will follow.",
        )

    def i_save_state(self) -> None:
        """Empty method as component has no state."""
        pass

    def i_restore_state(self) -> None:
        """Empty method as component has no state."""
        pass

    def i_prepare_simulation(self) -> None:
        """Prepares the simulation."""
        pass

    def i_doublecheck(self, timestep: int, stsv: cp.SingleTimeStepValues) -> None:
        """Gets called after the iterations are finished at each time step for potential debugging purposes."""
        pass

    def i_simulate(
        self, timestep: int, stsv: cp.SingleTimeStepValues, force_convergence: bool
    ) -> None:
        """Sets the current output values with data retrieved during initialization."""
        if self.ww_mass_input_channel.source_output is not None:
            # ww demand
            ww_temperature_demand = HouseholdWarmWaterDemandConfig.ww_temperature_demand

            # From Thermal Energy Storage
            ww_mass_input_per_sec = stsv.get_input_value(
                self.ww_mass_input_channel
            )  # kg/s
            # ww_mass_input = ww_mass_input_per_sec * self.seconds_per_timestep           # kg
            ww_mass_input: float = ww_mass_input_per_sec
            ww_temperature_input = stsv.get_input_value(
                self.ww_temperature_input_channel
            )  # °C

            # Information import
            freshwater_temperature = (
                HouseholdWarmWaterDemandConfig.freshwater_temperature
            )
            temperature_difference_cold = (
                HouseholdWarmWaterDemandConfig.temperature_difference_cold
            )
            energy_losses = 0
            specific_heat = 4180 / 3600

            ww_energy_demand = (
                specific_heat
                * self.water_consumption[timestep]
                * (ww_temperature_demand - freshwater_temperature)
            )

            if ww_energy_demand > 0 and (
                ww_mass_input == 0 and ww_temperature_input == 0
            ):
                """first iteration --> random numbers"""
                ww_temperature_input = 40.45
                ww_mass_input = 9.3

            """
            Warm water is provided by the warmwater stoage.
            The household needs water at a certain temperature. To get the correct temperature the amount of water from
            the wws is regulated and is depending on the temperature provided by the wws. The backflowing water to wws
            is cooled down to the temperature of (freshwater+temperature_difference_cold) --> ww_temperature_output.
            """
            if ww_energy_demand > 0:
                # heating up the freshwater. The mass is consistent
                energy_discharged = ww_energy_demand + energy_losses
                ww_temperature_output: float = (
                    freshwater_temperature + temperature_difference_cold
                )
                ww_mass_input = energy_discharged / (
                    PhysicsConfig.water_specific_heat_capacity_in_joule_per_kilogram_per_kelvin
                    * (ww_temperature_input - ww_temperature_output)
                )
            else:
                ww_temperature_output = ww_temperature_input
                ww_mass_input = 0
                energy_discharged = 0

        stsv.set_output_value(
            self.number_of_residents_channel, self.number_of_residents[timestep]
        )
        stsv.set_output_value(
            self.heating_by_residents_channel, self.heating_by_residents[timestep]
        )
        stsv.set_output_value(
            self.heating_by_devices_channel, self.heating_by_devices[timestep]
        )
        stsv.set_output_value(
            self.electricity_output_channel, self.electricity_consumption[timestep]
        )
        stsv.set_output_value(
            self.water_consumption_channel, self.water_consumption[timestep]
        )

        if self.config.predictive_control:
            last_forecast_timestep = int(
                timestep
                + 24 * 3600 / self.my_simulation_parameters.seconds_per_timestep
            )
            if last_forecast_timestep > len(self.electricity_consumption):
                last_forecast_timestep = len(self.electricity_consumption)
            demandforecast = self.electricity_consumption[
                timestep:last_forecast_timestep
            ]
            self.simulation_repository.set_entry(
                self.Electricity_Demand_Forecast_24h, demandforecast
            )

    def get_resolution(self) -> str:
        """Gets the temporal resolution of the simulation as a string in the format hh:mm:ss.

        :return: resolution of the simulation
        :rtype: str
        """
        seconds = self.my_simulation_parameters.seconds_per_timestep
        resolution = datetime.timedelta(seconds=seconds)
        return str(resolution)

    def get_profiles_from_utsp(
        self, lpg_households: Union[JsonReference, List[JsonReference]], guid: str
    ) -> Tuple[
        Union[str, List],
        Union[str, List],
        Union[str, List],
        Union[str, List],
        Union[str, List],
        List,
    ]:
        """Requests the required load profiles from a UTSP server. Returns raw, unparsed result file contents.

        :return: a tuple of all result file contents (electricity, warm water, high bodily activity and low bodily activity),
                 and a list of filenames of all additionally saved files
        """
        # Create an LPG configuration and set the simulation parameters
        start_date = self.my_simulation_parameters.start_date.strftime("%Y-%m-%d")
        # Unlike HiSim the LPG includes the specified end day in the simulation --> subtract one day
        last_day = self.my_simulation_parameters.end_date - datetime.timedelta(days=1)
        end_date = last_day.strftime("%Y-%m-%d")

        # choose if oen lpg request should be made or several in parallel
        if isinstance(lpg_households, JsonReference):

            simulation_config = self.prepare_lpg_simulation_config_for_utsp_request(
                start_date=start_date, end_date=end_date, household=lpg_households,
            )

            (
                electricity_file,
                warm_water_file,
                inner_device_heat_gains_file,
                high_activity_file,
                low_activity_file,
                saved_files,
            ) = self.calculate_one_lpg_request(
                simulation_config=simulation_config, guid=guid,
            )

        elif isinstance(lpg_households, List):

            simulation_configs = []
            for household in lpg_households:
                simulation_config = self.prepare_lpg_simulation_config_for_utsp_request(
                    start_date=start_date, end_date=end_date, household=household
                )
                simulation_configs.append(simulation_config)

            (
                electricity_file,
                warm_water_file,
                inner_device_heat_gains_file,
                high_activity_file,
                low_activity_file,
                saved_files,
            ) = self.calculate_multiple_lpg_requests(  # type: ignore
                url=self.utsp_url,
                api_key=self.utsp_api_key,
                lpg_configs=simulation_configs,
                guid=guid,
            )

        else:
            raise TypeError(
                f"Type of lpg_households {type(lpg_households)} is invalid. It should be a JSONReference or a list of JSONReference."
            )

        return (
            electricity_file,
            warm_water_file,
            inner_device_heat_gains_file,
            high_activity_file,
            low_activity_file,
            saved_files,
        )

    def get_profiles_from_predefined_profile(
        self,
    ) -> Tuple[
        str, str, str, str, str, List,
    ]:
        """Get the loadprofiles for a specific predefined profile from hisim/inputs/loadprofiles."""
        predefined_profile_filepaths = utils.HISIMPATH["occupancy"][
            "CHR01 Couple both at Work"
        ]
        # get first bodily activity files
        bodily_activity_filepaths = predefined_profile_filepaths["number_of_residents"]

        high_activity_file = bodily_activity_filepaths[0]
        low_activity_file = bodily_activity_filepaths[1]
        # get other files
        if self.utsp_config.profile_with_washing_machine_and_dishwasher:
            electricity_file = predefined_profile_filepaths["electricity_consumption"]
        else:
            electricity_file = predefined_profile_filepaths["electricity_consumption_without_washing_machine_and_dishwasher"]

        warm_water_file = predefined_profile_filepaths["water_consumption"]
        inner_device_heat_gains_file = predefined_profile_filepaths[
            "heating_by_devices"
        ]
        # when using predefined profile there are no saved files concerning flexibility or car data
        saved_files: List = []
        return (
            electricity_file,
            warm_water_file,
            inner_device_heat_gains_file,
            high_activity_file,
            low_activity_file,
            saved_files,
        )

    def save_result_file(self, name: str, content: str) -> str:
        """Saves a result file in the folder specified in the config object.

        :param name: the name for the file
        :type name: str
        :param content: the content that will be written into the file
        :type content: str
        :return: path of the file that was saved
        :rtype: str
        """
        try:
            filepath = os.path.join(self.utsp_config.result_dir_path, name)
        except Exception as exc:
            raise NameError(
                f"Could not create a filepath from config result_path {self.utsp_config.result_dir_path} and name {name}."
            ) from exc

        directory = os.path.dirname(filepath)
        # Create the directory if it does not exist
        try:
            os.makedirs(directory)
        except OSError as exc:
            if exc.errno == errno.EEXIST and os.path.isdir(directory):
                pass
            else:
                raise
        # Create the result file
        with open(filepath, "w", encoding="utf-8") as result_file:
            result_file.write(content)

        return filepath

    def build(self):
        """Retrieves and preprocesses all data for this component."""

        # check if file exists and get cache_filepath and put in list
        (
            list_of_file_exists_and_cache_files,
            list_of_unique_household_configs,
        ) = self.get_list_of_file_exists_bools_and_cache_file_paths(
            cache_dir_path=self.utsp_config.cache_dir_path
        )

        # go through list of file_exists and cache_filepaths and get caches if possible,
        # otherwise send request to UTSP
        cache_complete = False
        value_dict: Dict = {
            "electricity_consumption": [],
            "water_consumption": [],
            "heating_by_devices": [],
            "heating_by_residents": [],
            "number_of_residents": [],
        }
        # iterate over all unique utsp configs and either take cache results or calculate for each household and sum up later
        for list_index, list_item in enumerate(list_of_file_exists_and_cache_files):

            file_exists = list_item[0]
            cache_filepath = list_item[1]

            # a cache file exists
            if file_exists:
                with open(cache_filepath, "r", encoding="utf-8") as file:
                    cache_content: Dict = json.load(file)

                saved_files = cache_content["saved_files"]

                cache_complete = True
                # check if all of the additionally saved files that belong to the cached results
                # are also still there
                for filename in saved_files:

                    if not os.path.isfile(filename):
                        log.warning(
                            f"The cache file for {self.component_name} exists, "
                            f"but the result file {filename} in saved_files could not be found. "
                            "This is most likely because the file was voluntarily cleaned with the function cleanup_old_lpg_requests() in your system setup. "
                            "The results will not be taken from cache but requested freshly from utsp or taken from the predefined profile. "
                        )
                        cache_complete = False
                        break
                if cache_complete:
                    log.information("LPG data taken from cache. ")
                    cached_data = io.StringIO(cache_content["data"])
                    dataframe = pd.read_csv(
                        cached_data, sep=",", decimal=".", encoding="cp1252"
                    )

                    number_of_residents = dataframe["number_of_residents"].tolist()
                    heating_by_residents = dataframe["heating_by_residents"].tolist()
                    electricity_consumption = dataframe[
                        "electricity_consumption"
                    ].tolist()
                    water_consumption = dataframe["water_consumption"].tolist()
                    heating_by_devices = dataframe["heating_by_devices"].to_list()

                    number_of_residents = dataframe["number_of_residents"].tolist()

                    # write lists to dict
                    value_dict["electricity_consumption"].append(
                        electricity_consumption
                    )
                    value_dict["heating_by_devices"].append(heating_by_devices)
                    value_dict["heating_by_residents"].append(heating_by_residents)
                    value_dict["water_consumption"].append(water_consumption)
                    value_dict["number_of_residents"].append(number_of_residents)

                    # sum over all household profiles
                    (
                        self.electricity_consumption,
                        self.heating_by_residents,
                        self.water_consumption,
                        self.heating_by_devices,
                        self.number_of_residents,
                    ) = self.get_result_lists_by_summing_over_value_dict(
                        value_dict=value_dict
                    )

                    self.max_hot_water_demand = max(self.water_consumption)

            if not cache_complete or file_exists is False:
                log.information(
                    "LPG data cannot be taken from cache. It will be taken from UTSP or from predefined profile."
                )
                # if taking results from cache not possible, check lpg data acquition mode
                if self.utsp_config.data_acquisition_mode == LpgDataAcquisitionMode.USE_UTSP:
                    # try to get utsp url and api from .env if possible
                    try:
                        self.utsp_url = utils.get_environment_variable("UTSP_URL")
                        self.utsp_api_key = utils.get_environment_variable(
                            "UTSP_API_KEY"
                        )

                    except Exception:
                        log.warning(
                            "You chose USE_UTSP as data_acquition_mode but it is not possible to read the url and api_key from the .env file."
                            "Please check if this file is present in your system."
                            "Otherwise the predefined LPG profile in hisim/inputs/loadprofiles will be used."
                        )
                        self.utsp_config.data_acquisition_mode = (
                            LpgDataAcquisitionMode.USE_PREDEFINED_PROFILE
                        )

                if self.utsp_config.data_acquisition_mode == LpgDataAcquisitionMode.USE_UTSP:
                    log.information(
                        f"LPG data acquisition mode: {self.utsp_config.data_acquisition_mode}"
                    )
                    new_unique_config = list_of_unique_household_configs[list_index]

                    (
                        electricity_file,
                        warm_water_file,
                        inner_device_heat_gains_file,
                        high_activity_file,
                        low_activity_file,
                        saved_files,
                    ) = self.get_profiles_from_utsp(
                        lpg_households=new_unique_config.household,
                        guid=new_unique_config.guid,
                    )

                    # only one result obtained
                    if isinstance(electricity_file, str):

                        log.information("One result obtained from lpg utsp connector.")
                        (
                            electricity_consumption,
                            heating_by_devices,
                            water_consumption,
                            heating_by_residents,
                            number_of_residents,
                        ) = self.load_result_files_and_transform_to_lists(
                            electricity=electricity_file,
                            warm_water=warm_water_file,
                            inner_device_heat_gains=inner_device_heat_gains_file,
                            high_activity=high_activity_file,
                            low_activity=low_activity_file,
                            data_acquisition_mode=self.utsp_config.data_acquisition_mode,
                        )

                        # write lists to dict
                        value_dict["electricity_consumption"].append(
                            electricity_consumption
                        )
                        value_dict["heating_by_devices"].append(heating_by_devices)
                        value_dict["heating_by_residents"].append(heating_by_residents)
                        value_dict["water_consumption"].append(water_consumption)
                        value_dict["number_of_residents"].append(number_of_residents)

                        # cache results for each household individually
                        self.cache_results(
                            saved_files=saved_files,
                            cache_filepath=cache_filepath,
                            number_of_residents=number_of_residents,
                            electricity_consumption=electricity_consumption,
                            heating_by_residents=heating_by_residents,
                            water_consumption=water_consumption,
                            heating_by_devices=heating_by_devices,
                        )

                    # multiple results obtained (when multiple households in utsp_config given and the guid in the config is not "" but has a specific value)
                    elif isinstance(electricity_file, List):

                        log.information(
                            "Multiple results obtained from lpg utsp connector."
                        )

                        for index, electricity in enumerate(electricity_file):

                            warm_water = warm_water_file[index]
                            inner_device_heat_gains = inner_device_heat_gains_file[
                                index
                            ]
                            high_activity = high_activity_file[index]
                            low_activity = low_activity_file[index]

                            (
                                electricity_consumption,
                                heating_by_devices,
                                water_consumption,
                                heating_by_residents,
                                number_of_residents,
                            ) = self.load_result_files_and_transform_to_lists(
                                electricity=electricity,
                                warm_water=warm_water,
                                inner_device_heat_gains=inner_device_heat_gains,
                                high_activity=high_activity,
                                low_activity=low_activity,
                                data_acquisition_mode=self.utsp_config.data_acquisition_mode,
                            )

                            # write lists to dict
                            value_dict["electricity_consumption"].append(
                                electricity_consumption
                            )
                            value_dict["heating_by_devices"].append(heating_by_devices)
                            value_dict["heating_by_residents"].append(
                                heating_by_residents
                            )
                            value_dict["water_consumption"].append(water_consumption)
                            value_dict["number_of_residents"].append(
                                number_of_residents
                            )

                        # get sum of all household profiles
                        (
                            self.electricity_consumption,
                            self.heating_by_residents,
                            self.water_consumption,
                            self.heating_by_devices,
                            self.number_of_residents,
                        ) = self.get_result_lists_by_summing_over_value_dict(
                            value_dict=value_dict
                        )

                        self.max_hot_water_demand = max(self.water_consumption)

                        # cache for multiple results at a time
                        self.cache_results(
                            saved_files=saved_files[list_index],
                            cache_filepath=cache_filepath,
                            number_of_residents=self.number_of_residents,
                            heating_by_residents=self.heating_by_residents,
                            water_consumption=self.water_consumption,
                            heating_by_devices=self.heating_by_devices,
                            electricity_consumption=self.electricity_consumption,
                        )
                        break

                    # get sum of all household profiles
                    (
                        self.electricity_consumption,
                        self.heating_by_residents,
                        self.water_consumption,
                        self.heating_by_devices,
                        self.number_of_residents,
                    ) = self.get_result_lists_by_summing_over_value_dict(
                        value_dict=value_dict
                    )

                    self.max_hot_water_demand = max(self.water_consumption)

                elif (
                    self.utsp_config.data_acquisition_mode
                    == LpgDataAcquisitionMode.USE_PREDEFINED_PROFILE
                ):
                    log.information(
                        f"LPG data acquisition mode: {self.utsp_config.data_acquisition_mode}. "
                        "This means the predefined_lpg_household_chr01 from hisim/inputs/loadprofiles/ is taken."
                    )

                    (
                        electricity_file,
                        warm_water_file,
                        inner_device_heat_gains_file,
                        high_activity_file,
                        low_activity_file,
                        saved_files,
                    ) = self.get_profiles_from_predefined_profile()

                    (
                        self.electricity_consumption,
                        self.heating_by_devices,
                        self.water_consumption,
                        self.heating_by_residents,
                        self.number_of_residents,
                    ) = self.load_result_files_and_transform_to_lists(
                        electricity=electricity_file,
                        warm_water=warm_water_file,
                        inner_device_heat_gains=inner_device_heat_gains_file,
                        high_activity=high_activity_file,
                        low_activity=low_activity_file,
                        data_acquisition_mode=self.utsp_config.data_acquisition_mode,
                    )

                    self.max_hot_water_demand = max(self.water_consumption)

                    # when using the predefined household there are no saved_files
                    self.cache_results(
                        cache_filepath=cache_filepath,
                        number_of_residents=self.number_of_residents,
                        heating_by_residents=self.heating_by_residents,
                        water_consumption=self.water_consumption,
                        heating_by_devices=self.heating_by_devices,
                        electricity_consumption=self.electricity_consumption,
                        saved_files=[],
                    )

                    if self.utsp_config.predictive:
                        SingletonSimRepository().set_entry(
                            key=SingletonDictKeyEnum.HEATINGBYRESIDENTSYEARLYFORECAST,
                            entry=self.heating_by_residents,
                        )

    def get_result_lists_by_summing_over_value_dict(
        self, value_dict: Dict[Any, Any]
    ) -> Tuple[List, List, List, List, List]:
        """Get the result lists by summing over the value dict entries."""

        electricity_consumption = [
            sum(x) for x in zip(*value_dict["electricity_consumption"])
        ]
        heating_by_residents = [
            sum(x) for x in zip(*value_dict["heating_by_residents"])
        ]
        water_consumption = [sum(x) for x in zip(*value_dict["water_consumption"])]
        heating_by_devices = [sum(x) for x in zip(*value_dict["heating_by_devices"])]
        number_of_residents = [sum(x) for x in zip(*value_dict["number_of_residents"])]

        return (
            electricity_consumption,
            heating_by_residents,
            water_consumption,
            heating_by_devices,
            number_of_residents,
        )

    def write_to_report(self):
        """Adds a report entry for this component."""
        return self.utsp_config.get_string_dict()

    def get_cost_opex(
        self, all_outputs: List, postprocessing_results: pd.DataFrame,
    ) -> OpexCostDataClass:
        """Calculate OPEX costs, snd write total energy consumption to component-config.

        No electricity costs for components except for Electricity Meter,
        because part of electricity consumption is feed by PV
        """
        for index, output in enumerate(all_outputs):

            if (
                output.component_name == "UTSPConnector"
                and output.load_type == lt.LoadTypes.ELECTRICITY
            ):
                self.utsp_config.consumption = round(
                    sum(postprocessing_results.iloc[:, index])
                    * self.my_simulation_parameters.seconds_per_timestep
                    / 3.6e6,
                    1,
                )

        opex_cost_data_class = OpexCostDataClass(
            opex_cost=0, co2_footprint=0, consumption=self.utsp_config.consumption,
        )

        return opex_cost_data_class

    def get_list_of_file_exists_bools_and_cache_file_paths(
        self, cache_dir_path: Optional[str]
    ) -> Tuple[List, List]:
        """Check if file exists and get cache_filepath and put in list."""

        list_of_file_exists_and_cache_files: List = []
        list_of_unique_household_configs: List = []

        # check if cache_dir_path was chosen, otherwise use default cache_dir_path
        if cache_dir_path is None:
            cache_dir_path = os.path.join(utils.hisim_abs_path, "inputs", "cache")

        # config household is list of jsonreferences and no other guid than default is given ("")
        # if the guid = "" and multiple households are given as a list, each household will be calculated and cached individually
        if isinstance(self.utsp_config.household, List) and self.utsp_config.guid == "":
            # get specific guid list in order to prevent duplicated requests
            guid_list = (
                self.vary_guids_for_lpg_utsp_requests_if_config_household_is_a_list_and_contains_duplicated_household_types()
            )

            for index, household in enumerate(self.utsp_config.household):

                # make new config object with only one household in order to find local cache in cache_dir_path
                new_config_object = copy.deepcopy(self.utsp_config)
                new_config_object.household = household
                new_config_object.guid = guid_list[index]

                # check if cache for utsp config exists and get or make cache filepath
                file_exists, cache_filepath = utils.get_cache_file(
                    component_key=self.component_name,
                    parameter_class=new_config_object,
                    my_simulation_parameters=self.my_simulation_parameters,
                    cache_dir_path=cache_dir_path,
                )
                list_of_file_exists_and_cache_files.append(
                    [file_exists, cache_filepath]
                )
                list_of_unique_household_configs.append(new_config_object)

        # config household is one jsonreference
        else:

            file_exists, cache_filepath = utils.get_cache_file(
                component_key=self.component_name,
                parameter_class=self.utsp_config,
                my_simulation_parameters=self.my_simulation_parameters,
                cache_dir_path=cache_dir_path,
            )
            list_of_file_exists_and_cache_files.append([file_exists, cache_filepath])
            # ustp config is already unique because only 1 household in it
            list_of_unique_household_configs.append(self.utsp_config)

        return list_of_file_exists_and_cache_files, list_of_unique_household_configs

    def vary_guids_for_lpg_utsp_requests_if_config_household_is_a_list_and_contains_duplicated_household_types(
        self,
    ) -> List[str]:
        """In case the lpg_utsp_connector config is given a list of households, it will be checked if the list contains any duplicates.

        If so, for each duplicate the guid will be varied to make sure that each lpg request delivers a unique profile.
        """
        # check if household is list and return guid list
        if isinstance(self.utsp_config.household, List):
            copied_households = copy.deepcopy(self.utsp_config.household)
            guid_list = []

            for household in self.utsp_config.household:

                number_of_duplicated_households = copied_households.count(household)
                if number_of_duplicated_households == 1:
                    guid_list.append(str(1))
                elif number_of_duplicated_households > 1:
                    guid_list.append(str(number_of_duplicated_households))
                    copied_households.remove(household)

        return guid_list

    def calculate_one_lpg_request(
        self, simulation_config: HouseCreationAndCalculationJob, guid: str
    ) -> Tuple[str, str, str, str, str, List[str]]:
        """Calculate one lpg request."""

        # define required results files
        (
            result_files,
            electricity,
            warm_water,
            inner_device_heat_gains,
            high_activity,
            low_activity,
            flexibility,
            car_states,
            car_locations,
            driving_distances,
        ) = self.define_required_result_files()

        # Prepare the time series request
        request = datastructures.TimeSeriesRequest(
            simulation_config.to_json(), "LPG", required_result_files=result_files, guid=guid  # type: ignore
        )

        log.information("Requesting LPG profiles from the UTSP for one household.")

        # Request the time series
        result = client.request_time_series_and_wait_for_delivery(
            self.utsp_url, request, self.utsp_api_key, timeout=100
        )

        # decode required result files
        electricity_file = result.data[electricity].decode()
        warm_water_file = result.data[warm_water].decode()
        inner_device_heat_gains_file = result.data[inner_device_heat_gains].decode()
        high_activity_file = result.data[high_activity].decode()
        low_activity_file = result.data[low_activity].decode()

        saved_files: List[str] = []
        # try to decode and save optional flexibility result files if available
        try:
            flexibility_file = result.data[flexibility].decode()
            # Save flexibility
            path = self.save_result_file(name=flexibility, content=flexibility_file)
            saved_files.append(path)
        except Exception:
            pass

        # decode and save transportation files
        for filename in itertools.chain(
            car_states.keys(), car_locations.keys(), driving_distances.keys()
        ):
            if filename in result.data:
                path = self.save_result_file(
                    name=filename, content=result.data[filename].decode()
                )
                saved_files.append(path)

        return (
            electricity_file,
            warm_water_file,
            inner_device_heat_gains_file,
            high_activity_file,
            low_activity_file,
            saved_files,
        )

    def calculate_multiple_lpg_requests(
        self,
        lpg_configs: List,
        url: str,
        api_key: str,
        guid: str,
        raise_exceptions: bool = True,
        result_files: Any = None,
    ) -> Tuple[List[str], List[str], List[str], List[str], List[str], List[List[str]]]:
        """Sends multiple lpg requests for parallel calculation and collects their results."""

        (
            result_files,
            electricity,
            warm_water,
            inner_device_heat_gains,
            high_activity,
            low_activity,
            flexibility,
            car_states,
            car_locations,
            driving_distances,
        ) = self.define_required_result_files()

        # Create all request objects
        all_requests: List[TimeSeriesRequest] = [
            TimeSeriesRequest(
                config.to_json(), "LPG", required_result_files=result_files, guid=guid,
            )
            for config in lpg_configs
        ]

        log.information("Requesting LPG profiles from the UTSP for multiple household.")

        results = calculate_multiple_requests(
            url, all_requests, api_key, raise_exceptions,
        )

        # append all results in lists
        electricity_file: List = []
        warm_water_file: List = []
        inner_device_heat_gains_file: List = []
        high_activity_file: List = []
        low_activity_file: List = []
        saved_files: List = []

        for result in results:

            if isinstance(result, Exception):
                raise ValueError(
                    "result is an exception. Something went wrong during the utsp request."
                )

            electricity_file_one_result = result.data[electricity].decode()
            warm_water_file_one_result = result.data[warm_water].decode()
            inner_device_heat_gains_file_one_result = result.data[
                inner_device_heat_gains
            ].decode()
            high_activity_file_one_result = result.data[high_activity].decode()
            low_activity_file_one_result = result.data[low_activity].decode()

            saved_files_one_result: List = []
            # try to decode and save optional flexibility result files if available
            try:
                flexibility_file_one_result = result.data[flexibility].decode()
                # Save flexibility
                path = self.save_result_file(
                    name=flexibility, content=flexibility_file_one_result
                )
                saved_files_one_result.append(path)
            except Exception:
                pass

            # decode and save transportation files
            for filename in itertools.chain(
                car_states.keys(), car_locations.keys(), driving_distances.keys()
            ):
                if filename in result.data:
                    path = self.save_result_file(
                        name=filename, content=result.data[filename].decode()
                    )
                    saved_files_one_result.append(path)

            # append to lists
            electricity_file.append(electricity_file_one_result)
            warm_water_file.append(warm_water_file_one_result)
            inner_device_heat_gains_file.append(inner_device_heat_gains_file_one_result)
            high_activity_file.append(high_activity_file_one_result)
            low_activity_file.append(low_activity_file_one_result)
            saved_files.append(saved_files_one_result)

        return (
            electricity_file,
            warm_water_file,
            inner_device_heat_gains_file,
            high_activity_file,
            low_activity_file,
            saved_files,
        )

    def prepare_lpg_simulation_config_for_utsp_request(
        self, start_date: Any, end_date: Any, household: JsonReference
    ) -> HouseCreationAndCalculationJob:
        """Prepare lpg simulation config for the utsp request."""

        simulation_config = lpg_helper.create_basic_lpg_config(
            household,
            HouseTypes.HT23_No_Infrastructure_at_all,
            start_date,
            end_date,
            self.get_resolution(),
            travel_route_set=self.utsp_config.travel_route_set,
            transportation_device_set=self.utsp_config.transportation_device_set,
            charging_station_set=self.utsp_config.charging_station_set,
            calc_options=[
                CalcOption.HouseholdSumProfilesFromDetailedDats,
                CalcOption.HouseholdSumProfilesCsvNoFlex,
                CalcOption.BodilyActivityStatistics,
                CalcOption.TansportationDeviceJsons,
                CalcOption.FlexibilityEvents,
            ],
        )
        assert simulation_config.CalcSpec is not None

        # Enable simulation of transportation and flexible devices
        simulation_config.CalcSpec.EnableTransportation = True
        simulation_config.CalcSpec.EnableFlexibility = True

        return simulation_config

    def define_required_result_files(self):
        """Define required result files."""

        # Define required result files
        electricity = result_file_filters.LPGFilters.sum_hh1(
            LoadTypes.Electricity,
            no_flex=not self.utsp_config.profile_with_washing_machine_and_dishwasher,
        )
        warm_water = result_file_filters.LPGFilters.sum_hh1(
            LoadTypes.Warm_Water, no_flex=False
        )
        inner_device_heat_gains = result_file_filters.LPGFilters.sum_hh1(
            LoadTypes.Inner_Device_Heat_Gains, no_flex=False
        )
        high_activity = result_file_filters.LPGFilters.BodilyActivity.HIGH
        low_activity = result_file_filters.LPGFilters.BodilyActivity.LOW
        flexibility = result_file_filters.LPGFilters.FLEXIBILITY_EVENTS
        required_files = {
            f: datastructures.ResultFileRequirement.REQUIRED
            for f in [
                electricity,
                warm_water,
                inner_device_heat_gains,
                high_activity,
                low_activity,
            ]
        }
        optional_files = {flexibility: datastructures.ResultFileRequirement.OPTIONAL}
        # Define transportation result files
        car_states = result_file_filters.LPGFilters.all_car_states_optional()
        car_locations = result_file_filters.LPGFilters.all_car_locations_optional()
        driving_distances = (
            result_file_filters.LPGFilters.all_driving_distances_optional()
        )
        result_files: Dict[str, Optional[datastructures.ResultFileRequirement]] = {
            **required_files,
            **optional_files,
            **car_states,
            **car_locations,
            **driving_distances,
        }

        return (
            result_files,
            electricity,
            warm_water,
            inner_device_heat_gains,
            high_activity,
            low_activity,
            flexibility,
            car_states,
            car_locations,
            driving_distances,
        )

    def load_result_files_and_transform_to_lists(
        self,
        data_acquisition_mode: LpgDataAcquisitionMode,
        electricity: Any,
        warm_water: Any,
        inner_device_heat_gains: Any,
        high_activity: Any,
        low_activity: Any,
    ) -> tuple[List, List, List, List, List]:
        """Load result files and transform to lists."""

        ################################
        # Calculates heating generated by residents and loads number of residents
        # Heat power generated per resident in W
        # mode 1: awake
        # mode 2: sleeping
        gain_per_person = [150, 100]

        # load occupancy profile
        occupancy_profile = []
        bodily_activity_files = [high_activity, low_activity]
        for filecontent in bodily_activity_files:
            if data_acquisition_mode == LpgDataAcquisitionMode.USE_UTSP:
                json_filex = json.loads(filecontent)
            # this is used for files from predefined profile
            elif data_acquisition_mode == LpgDataAcquisitionMode.USE_PREDEFINED_PROFILE:
                with open(filecontent, encoding="utf-8") as json_file:
                    json_filex = json.load(json_file)
            else:
                raise ValueError("Could not recognize data_acquisition_mode.")

            occupancy_profile.append(json_filex)

        # see how long csv files from LPG are to check if averaging has to be done and calculate desired length
        simulation_time_span = (
            self.my_simulation_parameters.end_date
            - self.my_simulation_parameters.start_date
        )
        minutes_per_timestep = int(
            self.my_simulation_parameters.seconds_per_timestep / 60
        )
        steps_desired = int(
            simulation_time_span.days
            * 24
            * (3600 / self.my_simulation_parameters.seconds_per_timestep)
        )
        steps_desired_in_minutes = steps_desired * minutes_per_timestep

        # initialize number of residence and heating by residents
        heating_by_residents = [0.0] * steps_desired_in_minutes
        number_of_residents = [0] * steps_desired_in_minutes

        # compute heat gains and number of persons
        for mode, gain in enumerate(gain_per_person):
            for timestep in range(steps_desired_in_minutes):
                number_of_residents[timestep] += occupancy_profile[mode]["Values"][
                    timestep
                ]
                heating_by_residents[timestep] = (
                    heating_by_residents[timestep]
                    + gain * occupancy_profile[mode]["Values"][timestep]
                )
        if data_acquisition_mode == LpgDataAcquisitionMode.USE_UTSP:
            # load electricity consumption, water consumption and inner device heat gains
            electricity_data = io.StringIO(electricity)
            pre_electricity_consumption = pd.read_csv(
                electricity_data, sep=";", decimal=".", encoding="cp1252",
            ).loc[: (steps_desired_in_minutes - 1)]
            electricity_consumption_list = pd.to_numeric(
                pre_electricity_consumption["Sum [kWh]"] * 1000 * 60
            ).tolist()  # 1 kWh/min == 60W / min

            water_data = io.StringIO(warm_water)
            pre_water_consumption = pd.read_csv(
                water_data, sep=";", decimal=".", encoding="cp1252",
            ).loc[: (steps_desired_in_minutes - 1)]
            water_consumption_list = pd.to_numeric(
                pre_water_consumption["Sum [L]"]
            ).tolist()

            inner_device_heat_gain_data = io.StringIO(inner_device_heat_gains)
            pre_inner_device_heat_gains = pd.read_csv(
                inner_device_heat_gain_data, sep=";", decimal=".", encoding="cp1252",
            ).loc[: (steps_desired_in_minutes - 1)]
            inner_device_heat_gains_list = pd.to_numeric(
                pre_inner_device_heat_gains["Sum [kWh]"] * 1000 * 60
            ).tolist()  # 1 kWh/min == 60W / min

        elif data_acquisition_mode == LpgDataAcquisitionMode.USE_PREDEFINED_PROFILE:
            # load electricity consumption, water consumption and inner device heat gains
            pre_electricity_consumption = pd.read_csv(
                electricity,
                sep=";",
                decimal=".",
                encoding="utf-8",
                usecols=["Sum [kWh]"],
            ).loc[: (steps_desired_in_minutes - 1)]
            electricity_consumption_list = pd.to_numeric(
                pre_electricity_consumption.loc[:, "Sum [kWh]"] * 1000 * 60
            ).tolist()  # 1 kWh/min == 60 000 W / min

            pre_water_consumption = pd.read_csv(
                warm_water, sep=";", decimal=".", encoding="utf-8", usecols=["Sum [L]"],
            ).loc[: (steps_desired_in_minutes - 1)]
            water_consumption_list = pd.to_numeric(
                pre_water_consumption.loc[:, "Sum [L]"]
            ).tolist()

            pre_inner_device_heat_gains = pd.read_csv(
                inner_device_heat_gains,
                sep=";",
                decimal=".",
                encoding="utf-8",
                usecols=["Time", "Sum [kWh]"],
            ).loc[: (steps_desired_in_minutes - 1)]
            inner_device_heat_gains_list = pd.to_numeric(
                pre_inner_device_heat_gains.loc[:, "Sum [kWh]"] * 1000 * 60
            ).tolist()  # 1 kWh/min == 60W / min

        # put everything in a data frame and convert to utc
        initial_data = pd.DataFrame(
            {
                "Time": pd.date_range(
                    start=datetime.datetime(
                        year=self.my_simulation_parameters.year, month=1, day=1
                    ),
                    end=datetime.datetime(
                        year=self.my_simulation_parameters.year, month=1, day=1
                    )
                    + datetime.timedelta(days=simulation_time_span.days)
                    - datetime.timedelta(seconds=60),
                    freq="T",
                )
            }
        )

        initial_data["number_of_residents"] = number_of_residents
        initial_data["heating_by_residents"] = heating_by_residents
        initial_data["electricity_consumption"] = electricity_consumption_list
        initial_data["water_consumption"] = water_consumption_list
        initial_data["inner_device_heat_gains"] = inner_device_heat_gains_list

        initial_data = utils.convert_lpg_data_to_utc(
            data=initial_data, year=self.my_simulation_parameters.year
        )

        # extract everything from data frame
        electricity_consumption = initial_data["electricity_consumption"].tolist()
        heating_by_residents = initial_data["heating_by_residents"].tolist()
        number_of_residents = initial_data["number_of_residents"].tolist()
        water_consumption = initial_data["water_consumption"].tolist()
        heating_by_devices = initial_data["inner_device_heat_gains"].tolist()

        # average data, when time resolution of inputs is coarser than time resolution of simulation
        if minutes_per_timestep > 1:
            # power needs averaging, not sum
            electricity_consumption = [
                sum(electricity_consumption[n: n + minutes_per_timestep])
                / minutes_per_timestep
                for n in range(0, steps_desired_in_minutes, minutes_per_timestep)
            ]
            heating_by_devices = [
                sum(heating_by_devices[n: n + minutes_per_timestep])
                / minutes_per_timestep
                for n in range(0, steps_desired_in_minutes, minutes_per_timestep)
            ]
            water_consumption = [
                sum(water_consumption[n: n + minutes_per_timestep])
                for n in range(0, steps_desired_in_minutes, minutes_per_timestep)
            ]
            heating_by_residents = [
                sum(heating_by_residents[n: n + minutes_per_timestep])
                / minutes_per_timestep
                for n in range(0, steps_desired_in_minutes, minutes_per_timestep)
            ]
            number_of_residents = [
                int(
                    sum(number_of_residents[n: n + minutes_per_timestep])
                    / minutes_per_timestep
                )
                for n in range(0, steps_desired_in_minutes, minutes_per_timestep)
            ]

        return (
            electricity_consumption,
            heating_by_devices,
            water_consumption,
            heating_by_residents,
            number_of_residents,
        )

    def cache_results(
        self,
        cache_filepath: str,
        number_of_residents: List,
        heating_by_residents: List,
        electricity_consumption: List,
        water_consumption: List,
        heating_by_devices: List,
        saved_files: List,
    ) -> None:
        """Make caching file for the results."""

        # Saves data in cache
        database = pd.DataFrame(
            {
                "number_of_residents": number_of_residents,
                "heating_by_residents": heating_by_residents,
                "electricity_consumption": electricity_consumption,
                "water_consumption": water_consumption,
                "heating_by_devices": heating_by_devices,
            }
        )
        # dump the dataframe to str
        cache_file = io.StringIO()
        database.to_csv(cache_file)
        database_str = cache_file.getvalue()
        # save the dataframe and the list of additional files in the cache
        cache_content = {"saved_files": saved_files, "data": database_str}
        with open(cache_filepath, "w", encoding="utf-8") as file:
            json.dump(cache_content, file)
        del database

        log.information(
            f"Caching of lpg utsp results finished. Cache filepath is {cache_filepath}."
        )
