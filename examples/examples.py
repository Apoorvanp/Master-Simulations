# Generic
import numpy as np

# Owned
from simulator import Simulator
from component import SimulationParameters
from components.random_numbers import RandomNumbers
from components.transformer import Transformer
from components.sumbuilder import SumBuilderForTwoInputs
from components.advanced_battery import AdvancedBattery
import loadtypes
import globals

def first_example(my_sim: Simulator):
    """
    In this first example, a series (my_rn1) of random numbers in a range between 100 and 200 is
    summed up with a series (my_rn2) of random numbers in a range between 10 and 20. The result is
    a series (my_sum) with values between 110 and 220.
    """
    print("Starting first example: ")

    # Set the simulation parameters for the simulation
    my_sim_param: SimulationParameters = SimulationParameters.full_year(year=2021,
                                                                        seconds_per_timestep=60)     # Use a full year as timeline
    my_sim.set_parameters(my_sim_param)                                                              # Set timeline to simulator

    # Create first RandomNumbers object and adds to simulator
    my_rn1 = RandomNumbers(name="Random numbers 100-200",
                        timesteps=my_sim_param.timesteps,
                        minimum=100,
                        maximum=200)
    my_sim.add_component(my_rn1)

    # Create second RandomNumbers object and adds to simulator
    my_rn2 = RandomNumbers(name="Random numbers 10-20",
                        timesteps=my_sim_param.timesteps,
                        minimum=10,
                        maximum=20)
    my_sim.add_component(my_rn2)

    # Create sum builder object
    my_sum = SumBuilderForTwoInputs(name="Sum",
                                    loadtype=loadtypes.LoadTypes.Any,
                                    unit=loadtypes.Units.Any)
    # Connect inputs from sum object to both previous outputs
    my_sum.connect_input(input_fieldname=my_sum.SumInput1,
                         src_object_name=my_rn1.ComponentName,
                         src_field_name=my_rn1.RandomOutput)
    my_sum.connect_input(input_fieldname=my_sum.SumInput2,
                         src_object_name=my_rn2.ComponentName,
                         src_field_name=my_rn2.RandomOutput)
    my_sim.add_component(my_sum)

def second_example(my_sim: Simulator):
    """
    In this second example, two series (my_rn1 and my_transformer) are summed up.

    The first series (my_rn1) is a series of random numbers in a range between 100 and 200.
    The second series (my_transformer) is the result from a series (my_rn2) with random
    values between 10 and 20 after being applied a transformer. The transformer (my_transformer)
    amplifies the input values by 5 times. Hence, the second series has random values between 50 and 100.

    The result is a series (my_sum) with random values between 150 and 300.
    """
    print("Starting second example")

    # Set the simulation parameters for the simulation
    my_sim_param: SimulationParameters = SimulationParameters.full_year(year=2021,
                                                                        seconds_per_timestep=60)     # Use a full year as timeline
    my_sim.set_parameters(my_sim_param)                                                              # Set timeline to simulator

    # Create first RandomNumbers object and adds to simulator
    my_rn1 = RandomNumbers(name="Random numbers 100-200",
                           timesteps=my_sim_param.timesteps,
                           minimum=100,
                           maximum=200)
    my_sim.add_component(my_rn1)

    # Create second RandomNumbers object and adds to simulator
    my_rn2 = RandomNumbers(name="Random numbers 10-20",
                           timesteps=my_sim_param.timesteps,
                           minimum=10,
                           maximum=20)
    my_sim.add_component(my_rn2)

    # Create new Transformer object
    my_transformer = Transformer(name="MyTransformer")
    my_transformer.connect_input(input_fieldname=my_transformer.TransformerInput,         # Connect input from my transformer
                                 src_object_name=my_rn2.ComponentName,                    # to output of second random number object
                                 src_field_name=my_rn2.RandomOutput)
    my_sim.add_component(my_transformer)                                                  # Add my transformer to simulator

    # Create sum builder object
    my_sum = SumBuilderForTwoInputs(name="Sum",
                                    loadtype=loadtypes.LoadTypes.Any,
                                    unit=loadtypes.Units.Any)
    # Connect inputs from sum object to both previous outputs
    my_sum.connect_input(input_fieldname=my_sum.SumInput1,
                         src_object_name=my_rn1.ComponentName,
                         src_field_name=my_rn1.RandomOutput)
    my_sum.connect_input(input_fieldname=my_sum.SumInput2,
                         src_object_name=my_transformer.ComponentName,
                         src_field_name=my_transformer.TransformerOutput)
    my_sim.add_component(my_sum)