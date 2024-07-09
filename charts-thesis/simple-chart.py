import matplotlib.pyplot as plt
import numpy as np

# Data
profile_names = [
    'A couple at work', 
    'A couple with kid, one at work one at home', 
    'A single student'
]
profile_types = ['without PV', 'with PV', 'with PV and bidirectional charging']

total_electricity = [
    [9900.459745, 5588.941774, 4024.05993],
    [9258.301216, 5053.12205, 2966.549539],
    [2839.630476, 2505.182617, 2494.498637]
]

# Converting data to numpy array for easier manipulation
total_electricity = np.array(total_electricity)

# Define the bar width and positions
bar_width = 0.2
x = np.arange(len(profile_names))

# Create a figure and axis with smaller size
fig, ax = plt.subplots(figsize=(10, 6))

bars1 = ax.bar(x - bar_width, total_electricity[:, 0], bar_width, label='without PV', color='#FFA500', edgecolor='black')
bars2 = ax.bar(x, total_electricity[:, 1], bar_width, label='with PV', color='#FFD700', edgecolor='black')
bars3 = ax.bar(x + bar_width, total_electricity[:, 2], bar_width, label='with PV and bidirectional charging', color='#32CD32', edgecolor='black')


# Add value labels on top of the bars
for bars in [bars1, bars2, bars3]:
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{height:.0f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),  # 3 points vertical offset
                    textcoords="offset points",
                    ha='center', va='bottom')

# Add labels and title
ax.set_xlabel('Profile Name', fontweight='bold')
ax.set_ylabel('Total Electricity from Grid in kWh', fontweight='bold')
ax.set_title('Total Electricity from Grid by Profile Name and Type')
ax.set_xticks(x)
ax.set_xticklabels(profile_names, rotation=0, ha='center')  # Make profile names horizontal

# Add legend
ax.legend()

# Adjust layout and save the figure
plt.tight_layout()
plt.savefig('total_cost_grouped_bar_chart_horizontal.png', dpi=100)
plt.show()
