import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, ListedColormap

# Assuming the Carpet class is defined here
class Carpet:
    def __init__(
        self,
        output,
        component_name,
        units,
        directory_path,
        time_correction_factor,
        output_description,
        figure_format,
    ):
        self.output = output
        self.component_name = component_name
        self.units = units
        self.directory_path = directory_path
        self.time_correction_factor = time_correction_factor
        self.output_description = output_description
        self.figure_format = figure_format
        self.figsize = (12, 8)  # Example figsize
        self.dpi = 100  # Example dpi
        self.fontsize_label = 14  # Example fontsize for labels
        self.fontsize_title = 16  # Example fontsize for title
        self.fontsize_ticks = 12  # Example fontsize for ticks
        self.title = "Electricity Consumption from Grid".upper()  # Example title
        self.filepath2 = "carpet_plot.png"  # Example file path for saving the plot
        self.months_abbrev_uppercase = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

    def plot(self, xdims, data):
        ydims = int(len(data) / xdims)  # number of calculated timesteps per day
        y_steps_per_hour = int(ydims / 24)

        try:
            database = data.values.reshape(xdims, ydims)
        except ValueError:
            print("Carpet plot can only deal with data containing entire days")
            return

        if np.max(np.abs(data.values)) > 1.5e3:
            database = database * 1e-3
            self.units = f"k{self.units}"

        plot_data = np.flip(database.transpose(), axis=0)

        fig = plt.figure(figsize=self.figsize, dpi=self.dpi)
        axis = fig.add_subplot(111)

        # Define a custom colormap
        colors = [(1, 1, 1), (0.8, 0.9, 0.9), (0.6, 0.8, 0.8), (0.4, 0.6, 0.6), (0.2, 0.4, 0.4), (0, 0.2, 0.2)]
        custom_cmap = LinearSegmentedColormap.from_list("custom_cmap", colors, N=256)

        plot = axis.pcolormesh(plot_data, cmap=custom_cmap)
        plt.colorbar(plot).set_label(self.units, fontsize=self.fontsize_label)

        y_ticks = np.arange(0, 25 * y_steps_per_hour, 6 * y_steps_per_hour).tolist()
        axis.set_yticks(y_ticks)
        y_ticks_labels = np.flip(list(range(0, 25, 6)), axis=0)
        axis.set_yticklabels([str(i).upper() for i in y_ticks_labels], fontsize=self.fontsize_ticks)

        if xdims == 365:
            x_ticks = np.arange(15, 346, 30).tolist()
            axis.set_xticks(x_ticks)
            axis.set_xticklabels([str(i).upper() for i in self.months_abbrev_uppercase], fontsize=self.fontsize_ticks)

        fig.autofmt_xdate(rotation=45)
        axis.set_ylabel("TIME OF DAY [H]", fontsize=self.fontsize_label)
        axis.set_xlabel("MONTH OF THE YEAR", fontsize=self.fontsize_label)
        plt.title(self.title, fontsize=self.fontsize_title)
        plt.xticks(fontsize=self.fontsize_ticks)
        plt.yticks(fontsize=self.fontsize_ticks)
        plt.tight_layout()
        plt.savefig(self.filepath2)
        plt.close()

        return self.filepath2

# Load the data
file_path = '/Users/apoorvanp/workspace/HiSim/charts-thesis/ElectricityFromGrid_ElectricityMeter.csv'
data = pd.read_csv(file_path)

# Convert the timestamp to a datetime object
data['timestamp'] = pd.to_datetime(data['Unnamed: 0'])
data.set_index('timestamp', inplace=True)

# Remove duplicate timestamps by averaging their values
data = data.groupby(data.index).mean(numeric_only=True)

# Resample the data to hourly means
hourly_data = data.resample('h').mean()

# Instantiate the Carpet class and plot
carpet_plotter = Carpet(
    output=None,
    component_name="ElectricityFromGrid",
    units="Wh",
    directory_path=".",
    time_correction_factor=1.0,
    output_description="Electricity consumption from the grid",
    figure_format="png"
)

# Determine the number of days in the dataset
xdims = len(hourly_data) // 24  # Assuming data for entire days

# Plot the carpet plot
carpet_plotter.plot(xdims, hourly_data['ElectricityMeter - ElectricityFromGrid [Electricity - Wh]'])
