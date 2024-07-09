import matplotlib.pyplot as plt
import numpy as np

# Data
profile_names = [
    'A couple at work', 
    'A couple with kid, one at work one at home', 
    'A single student'
]

profile_types = ['without PV', 'with PV', 'with PV and bidirectional charging']

total_costs = [
    [3960.183898, 1823.475148, 1112.382952],
    [3703.320486, 1598.183103, 753.9225061],
    [1135.852191, 978.3047269, 972.672555]
]

# Converting data to numpy array for easier manipulation
total_costs = np.array(total_costs)

# Define the bar width and positions
bar_width = 0.2
x = np.arange(len(profile_names))

# Create a figure and axis with smaller size
fig, ax = plt.subplots(figsize=(10, 6))

# Plotting the grouped bar chart with original colors
bars1 = ax.bar(x - bar_width, total_costs[:, 0], bar_width, label='without PV', color='#FFA500', edgecolor='black')
bars2 = ax.bar(x, total_costs[:, 1], bar_width, label='with PV', color='#FFD700', edgecolor='black')
bars3 = ax.bar(x + bar_width, total_costs[:, 2], bar_width, label='with PV and bidirectional charging', color='#32CD32', edgecolor='black')

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
ax.set_ylabel('Total Cost in Euros', fontweight='bold')
ax.set_title('Total Cost by Profile Name and Type')
ax.set_xticks(x)
ax.set_xticklabels(profile_names, rotation=0, ha='center')  # Make profile names horizontal

# Add legend
ax.legend()

# Adjust layout and save the figure
plt.tight_layout()
plt.savefig('total_cost_grouped_bar_chart_horizontal.png', dpi=100)
plt.show()
