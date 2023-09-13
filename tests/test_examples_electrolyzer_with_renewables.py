""" Tests for the electrolyzer with renewables example. """

import os
import pytest

from hisim import hisim_main
from hisim.simulationparameters import SimulationParameters
from hisim import log
from hisim import utils

@pytest.mark.examples
@utils.measure_execution_time
def test_electrolyzer_with_renewables():
    """ Single day. """
    path = "../examples/electrolyzer_with_renewables.py"
    func = "electrolyzer_example"
    mysimpar = SimulationParameters.one_day_only(year=2021, seconds_per_timestep=60)
    hisim_main.main(path, func, mysimpar)
    log.information(os.getcwd())