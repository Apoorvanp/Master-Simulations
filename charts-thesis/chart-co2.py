import matplotlib.pyplot as plt
import numpy as np

# Data
profile_names = [
    'A couple at work', 
    'A couple with kid, one person at work one at home', 
    'A single male student'
]

profile_types = ['without PV', 'with PV', 'with bidirectional charging']

co2_emissions = [
    [3960183.898, 2235576.71, 1609623.972],
    [3703320.486, 2021248.82, 1186619.816],
    [1135852.191, 1002073.047, 997799.4548]
]

# Plotting the activity chart
fig, ax = plt.subplots(figsize=(10, 6))

# Define x positions for the profile names
x_positions = np.arange(len(profile_names))

# Plot the points
for i, profile_name in enumerate(profile_names):
    ax.plot([x_positions[i]]*3, co2_emissions[i], 'o-', label=profile_name if i == 0 else "")

# Add arrows to indicate transitions
for i in range(len(profile_names)):
    ax.annotate(
        '', xy=(x_positions[i], co2_emissions[i][1]), xytext=(x_positions[i], co2_emissions[i][0]),
        arrowprops=dict(arrowstyle="->", color='blue')
    )
    ax.annotate(
        '', xy=(x_positions[i], co2_emissions[i][2]), xytext=(x_positions[i], co2_emissions[i][1]),
        arrowprops=dict(arrowstyle="->", color='green')
    )

# Add labels and title
ax.set_xticks(x_positions)
ax.set_xticklabels(profile_names, rotation=45, ha='right')
ax.set_xlabel('Profile Name', fontweight='bold')
ax.set_ylabel('CO2 Emissions in g')
ax.set_title('CO2 Emissions Transition by Profile Name and Type')

# Add legend
ax.legend()

# Adjust layout and save the figure
plt.tight_layout()
plt.savefig('co2_emissions_activity_chart.png', dpi=100)
plt.show()
