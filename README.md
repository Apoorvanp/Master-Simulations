# HiSim - Household Infrastructure and Building Simulator

HiSim is a Python package for simulation and analysis of household scenarios and building systems using modern
components as alternative to fossil fuel based ones. This package integrates load profiles generation of electricity
consumption, heating demand, electricity generation, and strategies of smart strategies of modern components, such as
heat pump, battery, electric vehicle or thermal energy storage. HiSim is a package under development by
Forschungszentrum Jülich und Hochschule Emden/Leer. For detailed documentation, please
access [ReadTheDocs](https://household-infrastructure-simulator.readthedocs.io/en/latest/) of this repository.


# Install Graphviz

If you want to use the feature that generates system charts, you need to install GraphViz in your system. If you don't
have Graphviz installed, you will experience error messages about a missing dot.exe under Windows.

Follow the installation instructions from here:
https://www.graphviz.org/download/

(or simply disable the system charts)

Clone repository
-----------------------
To clone this repository, enter the following command to your terminal:

```python
git clone https://github.com/Apoorvanp/Master-Simulations.git
```

Virtual Environment
-----------------------
Before installing `Hisim`, it is recommended to set up a Python virtual environment. Let `hisimvenv` be the name of
virtual environment to be created. For Windows users, setting the virtual environment in the path `\Hisim` is done with
the command line:

```python
python -m venv hisimvenv
```

For Linux/Mac users, the virtual environment is set up and activated as follows:

```python 
source hisimvenv/bin/activate
```

Alternatively, Anaconda can be used to set up and activate the virtual environment:

```python 
conda create -n hisimvenv python=3.9
conda activate hisimvenv
```

With the successful activation, `HiSim` is ready to be locally installed.

Install package
------------------------
After setting up the virtual environment, install the package to your local libraries:

```python
pip install -e .
```

Optional: Set environment variables
-----------------------
Certain components might access APIs to retrieve data. In order to use them, you need to set the url and key as environment variables. This can be done with an `.env` file wihtin the HiSim root folder or with system tools. The environment variables are:

```
UTSP_URL="http://134.94.131.167:443/api/v1/profilerequest"
UTSP_API_KEY="OrjpZY93BcNWw8lKaMp0BEchbCc"
```

Run simulations for the following household setups
-----------------------

This branch includes the files to run the simulations for "A couple at work" and "A couple with a kid, one at work and one at home". 

The following scenario is included for "A couple at work" household profile in Hamburg, Germany
* With 10kW peak PV and 10kWh battery and bidirectional charger for EV
Run the python interpreter in the `HiSim/system_setups` directory with the following command:
```python
python ./hisim/hisim_main.py ./system_setups/run_couple_at_work_bidirectional.py
```

The following scenarios are included for "A couple with a kid, one at work and one at home" household profile in Hamburg, Germany
* With 10kW peak PV and 10kWh battery and bidirectional charger for EV
Run the python interpreter in the `HiSim/system_setups` directory with the following command:
```python
python ./hisim/hisim_main.py ./system_setups/run_couple_with_kid_bidirectional.py
```

This command executes `hisim_main.py` on the python files implemented for each household type and scenario. The results can be visualized under directory `results`. 

New simulations and household profile can be created by going through the simulations as part of the thesis and the HiSim docs.

