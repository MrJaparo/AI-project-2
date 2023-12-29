import threading
import tkinter as tk
from tkinter import Button, Label, StringVar, ttk, filedialog
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from numpy.ma.core import ceil
from pandasgui import gui
from scipy.spatial import distance
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
import matplotlib.colors as mcolors
from ucimlrepo import fetch_ucirepo

# Global variables
is_paused = True
progress_var = None
som = None
label_map = None
fig = None
df_table = [pd.DataFrame()]  # Initialize df_table as a list containing an empty DataFrame

def minmax_scaler(data):
    # Separate numeric and non-numeric columns
    numeric_cols = data.select_dtypes(include=np.number).columns
    non_numeric_cols = list(set(data.columns) - set(numeric_cols))

    # Scale numeric columns
    numeric_data = data[numeric_cols]
    scaler = MinMaxScaler()
    scaled_numeric = scaler.fit_transform(numeric_data)

    # Check for and replace NaN and infinite values
    scaled_numeric = np.nan_to_num(scaled_numeric)

    # One-hot encode non-numeric columns
    non_numeric_data = pd.get_dummies(data[non_numeric_cols])

    # Concatenate scaled numeric and one-hot encoded non-numeric data
    scaled_data = np.concatenate([scaled_numeric, non_numeric_data], axis=1)

    return scaled_data

def evaluate_risk(data, symboling_col, normalized_losses_col):
    # Function to evaluate risk based on symboling and normalized losses
    risk = np.zeros(len(data))

    # Adjust risk based on symboling
    risk += data[symboling_col]

    # Adjust risk based on normalized losses
    risk += data[normalized_losses_col]

    return risk

def e_distance(x, y):
    if x.ndim > 1:
        x = x.flatten()
    if y.ndim > 1:
        y = y.flatten()
    return distance.euclidean(x, y)

def m_distance(x, y):
    return distance.cityblock(x, y)

def winning_neuron(data, t, som, num_rows, num_cols):
    winner = [0, 0]
    shortest_distance = np.sqrt(data.shape[1])
    input_data = data[t][:, np.newaxis] if data[t].ndim == 1 else data[t]
    for row in range(num_rows):
        for col in range(num_cols):
            dist = e_distance(som[row][col], input_data)
            if dist < shortest_distance:
                shortest_distance = dist
                winner = [row, col]
    return winner

def decay(step, max_steps, max_learning_rate, max_neighbourhood_range):
    coefficient = 1.0 - (np.float64(step) / max_steps)
    learning_rate = coefficient * max_learning_rate
    neighbourhood_range = ceil(coefficient * max_neighbourhood_range)
    return learning_rate, neighbourhood_range

def som_training(train_data, num_rows, num_cols, max_neighbourhood_range, max_learning_rate, max_steps, label_var,
                 train_y=None):
    global som, label_map
    num_dims = train_data.shape[1]
    np.random.seed(40)
    som = np.random.random_sample(size=(num_rows, num_cols, num_dims))

    for step in range(max_steps):
        if is_paused:
            continue  # Skip the iteration if paused

        progress_var.set((step + 1) / max_steps * 100)  # Update progress bar

        if (step + 1) % 1000 == 0:
            label_var.set(f"Iteration: {step + 1}")
            root.update()  # Update the Tkinter GUI

        learning_rate, neighbourhood_range = decay(step, max_steps, max_learning_rate, max_neighbourhood_range)

        t = np.random.randint(0, high=train_data.shape[0])
        winner = winning_neuron(train_data, t, som, num_rows, num_cols)

        for row in range(num_rows):
            for col in range(num_cols):
                if m_distance([row, col], winner) <= neighbourhood_range:
                    som[row][col] += learning_rate * (train_data[t] - som[row][col])

    print("SOM training completed")
    label_var.set("SOM training completed")

    label_map = label_som_nodes(train_data, train_y, num_rows, num_cols, som)
    return som, label_map

def label_som_nodes(train_data_norm, train_y, num_rows, num_cols, som):
    label_map = np.full((num_rows, num_cols), None, dtype=object)

    for t in range(train_data_norm.shape[0]):
        winner = winning_neuron(train_data_norm, t, som, num_rows, num_cols)
        row, col = winner
        label = train_y.iloc[t].item()

        if label_map[row, col] is None:
            label_map[row, col] = {label: 1}
        else:
            label_counts = label_map[row, col]
            if label in label_counts:
                label_counts[label] += 1
            else:
                label_counts[label] = 1

    for i in range(num_rows):
        for j in range(num_cols):
            if label_map[i, j] is not None:
                label_map[i, j] = max(label_map[i, j], key=label_map[i, j].get)

    return label_map

def evaluate_accuracy(test_data, test_y, som, label_map, num_rows, num_cols):
    winner_labels = []

    for t in range(test_data.shape[0]):
        input_data = test_data[t][:, np.newaxis] if test_data[t].ndim == 1 else test_data[t]
        winner = winning_neuron(input_data, t, som, num_rows, num_cols)
        row = winner[0]
        col = winner[1]
        predicted = label_map[row][col]

        if predicted is None:
            predicted = 'default_label'

        winner_labels.append(predicted)

    unique_labels_test = np.unique(test_y)
    label_dict_test = {label: idx for idx, label in enumerate(unique_labels_test)}

    winner_labels_numeric = np.array([label_dict_test.get(label, len(unique_labels_test)) for label in winner_labels])

    if 'default_label' not in label_dict_test:
        winner_labels_numeric[winner_labels_numeric == len(unique_labels_test)] = -1

    accuracy = accuracy_score(test_y, winner_labels_numeric)
    return accuracy

def show_pandasgui():
    gui_instance = gui.show(df_table[0], title="SOM Results")
    save_button = tk.Button(gui_instance.root, text="Save to CSV", command=lambda: save_to_csv(df_table[0]))
    save_button.pack(side=tk.BOTTOM)

def save_to_csv(df):
    file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
    if file_path:
        df.to_csv(file_path, index=False)
        print(f"Results saved to: {file_path}")

def display_som_plot_gui_func(label_map, max_steps):
    global root, fig
    cmap = mcolors.ListedColormap(
        ['white', 'black', 'red', 'green', 'blue', 'yellow', 'purple', 'orange', 'brown', 'pink'])

    if label_map is None:
        print("Error: label_map is None. Make sure SOM training is completed.")
        return

    label_map_numeric = np.zeros_like(label_map, dtype=float)
    unique_labels = np.unique([label for row in label_map for label in row if label is not None])

    if unique_labels.size == 0:
        print("Error: No unique labels found in label_map.")
        return

    label_dict = {label: idx for idx, label in enumerate(unique_labels)}

    for i in range(label_map.shape[0]):
        for j in range(label_map.shape[1]):
            if label_map[i, j] is not None:
                label_map_numeric[i, j] = label_dict[label_map[i, j]]

    fig, ax = plt.subplots(2, 1, gridspec_kw={'height_ratios': [4, 1]})

    im = ax[0].imshow(label_map_numeric, cmap=cmap)
    cbar = plt.colorbar(im, ax=ax[0], ticks=range(len(unique_labels)), label='Risk Analysis')  # Updated label here
    ax[0].set_title(f'SOM after {max_steps} iterations')  # Updated title here

    label_counts = [np.sum(label_map == label) for label in unique_labels]
    colors = plt.cm.viridis(np.linspace(0, 1, len(unique_labels)))

    ax[1].barh(unique_labels, label_counts, color=colors)
    ax[1].set_yticks(unique_labels)
    ax[1].set_ylabel('Risk Analysis')
    ax[1].set_xlabel('Frequency')

    canvas = FigureCanvasTkAgg(fig, master=root)
    canvas_widget = canvas.get_tk_widget()
    canvas_widget.pack()

    download_button = Button(root, text="Download Graph", command=lambda: download_graph(fig))
    download_button.pack()

    def update_canvas():
        canvas.draw()

    root.after(100, update_canvas)

    def download_graph(figure):
        file_path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG files", "*.png")])
        if file_path:
            figure.savefig(file_path, bbox_inches='tight')
            print(f"Graph saved to: {file_path}")

def load_uci_dataset_to_pandasgui(UCI_DATASET_ID):
    global df_table, root

    dataset = fetch_ucirepo(id=10)

    # Assuming 'data' is the dataset features and 'target' is the dataset target
    data = dataset.data.features
    target = dataset.data.targets

    # Concatenate features and target to create a DataFrame
    df = pd.concat([pd.DataFrame(data), pd.DataFrame(target, columns=['Target'])], axis=1)

    # Display the DataFrame using PandasGUI
    gui_instance = gui.show(df, title=f"UCI Dataset - {dataset.name}")

    # Add a button to save the DataFrame to a CSV file
    save_button = tk.Button(gui_instance.root, text="Save to CSV", command=lambda: save_to_csv(df))
    save_button.pack(side=tk.BOTTOM)

    # Run the Tkinter main loop
    root.mainloop()

def initialize_gui(show_table=None, show_pandasgui_button=True):  # Added the show_pandasgui_button parameter
    global root
    root = tk.Tk()
    root.title("SOM Training GUI")

    label_var = StringVar()
    label_var.set("Press the button to start SOM training")
    label = Label(root, textvariable=label_var)
    label.pack()

    button = Button(root, text="Start SOM Training", command=lambda: on_button_click(label_var, show_pandasgui_button))  # Pass show_pandasgui_button
    button.pack()

    pause_button = Button(root, text="Pause", command=on_pause_click)
    pause_button.pack()

    if show_pandasgui_button:  # Only add the button if show_pandasgui_button is True
        show_pandasgui_button = Button(root, text="Show with PandasGUI", command=show_pandasgui)
        show_pandasgui_button.pack()

    load_uci_button = Button(root, text="Show Table",
                             command=lambda: load_uci_dataset_to_pandasgui(UCI_DATASET_ID))
    load_uci_button.pack()

    root.mainloop()

def on_button_click(label_var, show_pandasgui_button):
    global is_paused, progress_var, root, som, label_map, df_table
    is_paused = False
    progress_var = tk.DoubleVar()
    progress_bar = ttk.Progressbar(root, variable=progress_var, maximum=100)
    progress_bar.pack()

    som_thread = threading.Thread(target=som_training_thread, args=(label_var, show_pandasgui_button))  # Pass show_pandasgui_button
    som_thread.start()

def on_pause_click():
    global is_paused
    is_paused = not is_paused

def som_training_thread(label_var, show_pandasgui_button):
    global som, label_map, root, fig

    automobile = fetch_ucirepo(id=10)
    X = automobile.data.features
    y = automobile.data.targets

    train_x, test_x, train_y, test_y = train_test_split(X, y, test_size=0.2, random_state=42)
    print(train_x.shape, train_y.shape, test_x.shape, test_y.shape)

    if train_y is None:
        print("Error: 'train_y' is None. Make sure the dataset is loaded correctly.")
        return

    if show_pandasgui_button:  # Check if show_pandasgui_button is True
        # Display PandasGUI with SOM results
        gui.show(df_table[0], title="SOM Results", mode='block')

    num_rows = 10
    num_cols = 10
    max_neighbourhood_range = 4
    max_learning_rate = 0.5
    max_steps = int(7.5 * 10e3)

    train_data = pd.concat([train_x, train_y], axis=1)
    train_data_norm = minmax_scaler(train_data)
    som, label_map = som_training(train_data_norm, num_rows, num_cols, max_neighbourhood_range,
                                  max_learning_rate, max_steps, label_var, train_y)

    # Print SOM result
    print("Label Map:")
    print(label_map)

    test_data_norm = minmax_scaler(test_x)
    accuracy = evaluate_accuracy(test_data_norm, test_y, som, label_map, num_rows, num_cols)
    print(f"Accuracy on Test Set: {accuracy:.2%}")

    # Display the SOM plot and label distribution
    display_som_plot_gui_func(label_map, max_steps)

    if show_pandasgui_button:  # Check if show_pandasgui_button is True
        # Display PandasGUI with SOM results
        gui.show(df_table[0], title="SOM Results", mode='block')


if __name__ == "__main__":
    # Set the UCI dataset ID for the function load_uci_dataset_to_pandasgui
    UCI_DATASET_ID = 10  # Change this ID based on the desired UCI dataset

    # Initialize GUI with the option to show PandasGUI
    initialize_gui(show_table=show_pandasgui, show_pandasgui_button=False)