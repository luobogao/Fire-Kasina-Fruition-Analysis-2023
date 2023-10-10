import os
import sys
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

rolling_avg_seconds = 10
window_size = 5  # Rolling average
fruition_window = 50
take_every_nth_row = 1
line_alpha = 0.1
num_clusters = 2
std_dev_threshold = 1.5   # Sensitivity to outlier detection - some fruition ranges have extreme data

# DataFrame to hold all windowed data
all_windows_df = pd.DataFrame()

x_values_full = range(-window_size, window_size + 1)  # +1 to include the upper bound
x_values = x_values_full[::take_every_nth_row]  # Sub-sample x_values to match y-values

# NOT CURRENTLY USED
def trimmed_mean(values, percentage=10):
    n = len(values)
    k = int(n * percentage / 100)
    return np.mean(np.sort(values)[k:-k])


def plot_data_from_csv(data_path):
  
    # Load the data
    print(f"Processing {data_path}")
    data = pd.read_csv(data_path)

    # Identify columns to check for NaN, excluding 'notes'
    columns_to_check = [col for col in data.columns if col != 'notes']

    # Remove rows where any of the columns_to_check have NaN values
    clean = data.dropna(subset=columns_to_check)

    global all_windows_df

    # Identify all rows where 'FRUITION-CALC' appears in the 'notes' column
    event_rows = data[data['notes'] == 'FRUITION-CALC'].index

    # Define columns to exclude and determine columns to plot
    exclude_columns = ['Fp1', 'Fp2', 'F7', 'F8', 'F3', 'F4', 'Fz', "ExG 1", "Var Fp1", 'notes']
    columns_to_plot = [col for col in data.columns[1:] if col not in exclude_columns]

    # Define a color map
    
    all_rolling_avgs = []

    
    for idx, row in enumerate(event_rows):
      window_data = data.loc[row-fruition_window:row+fruition_window, columns_to_plot]          
      if (row < window_size):
        print(f"Skipping row {row} in {data_path} as it does not have enough data.")
        continue
      else:        
        avg_values = window_data.mean(axis=1)
        rolling_avg = avg_values.rolling(window=rolling_avg_seconds).mean().shift(int(-1/2 * rolling_avg_seconds))
        all_rolling_avgs.append (rolling_avg)
        # Concatenate the window data as a new column in the DataFrame        
        col_name = f"{os.path.splitext(os.path.basename(data_path))[0]}_Fruition_{idx + 1}"
        new_val = np.round(window_data.mean(axis=1).reset_index(drop=True))  # Reset index for proper alignment
        if (new_val.isna().any()):
          print(f"Skipping row {row} in {data_path} as it has NaN values.")
          continue
        else:
          all_windows_df[col_name] = new_val



    return all_rolling_avgs

if __name__ == '__main__':

  if len(sys.argv) < 2:
    print("Please provide the folder path containing the CSV files as an argument.")
    sys.exit()

  folder_path = sys.argv[1]


  
  all_curves = []
  for csv_file in os.listdir(folder_path):
    if csv_file.endswith('.csv'):
      rolling_avgs = plot_data_from_csv(os.path.join(folder_path, csv_file))
      for avg in rolling_avgs:
        x_range = range(-fruition_window, -fruition_window + len(avg))        
        all_curves.append(avg)
  
  # Convert the list of all curves to a 2D NumPy array
  all_curves_np = np.zeros((len(all_curves), (fruition_window * 2) + 1))
  for i, curve in enumerate(all_curves):    
    offset = max(0, fruition_window - curve.index[0])
    length = min((fruition_window * 2) + 1 - offset, len(curve))

    
    if length <= 0:
        print(f"Error: curve.index[0]={curve.index[0]}, offset={offset}, length={length}")
        continue
    all_curves_np[i, offset:offset+length] = curve.values[:length]


  all_windows_df.to_csv("all_fruition_events.csv", index=False)

  # Step 1: Clustering
  kmeans = KMeans(n_clusters=num_clusters, random_state=42)
  clusters = kmeans.fit_predict(all_windows_df.T)  

  # Step 2: PCA for Outlier Removal
  pca = PCA(n_components=2)
  reduced_data = pca.fit_transform(all_windows_df.T)

  # Calculate the Euclidean distance of each point from the origin in the PCA space
  distances_from_origin = np.sqrt((reduced_data ** 2).sum(axis=1))

  # Identify the outlier: the point that is furthest from the origin
  outlier_index = np.argmax(distances_from_origin)

  # Remove the outlier from the data and re-cluster
  clean_data = all_windows_df.T.drop(index=all_windows_df.T.index[outlier_index])  
  clean_clusters = kmeans.fit_predict(clean_data)  

  # Step 3: PCA Visualization with Cleaned Data
  pca_clean = PCA(n_components=2)
  reduced_data_clean = pca_clean.fit_transform(clean_data)  

  # plt.figure(figsize=(10, 6))
  # plt.scatter(reduced_data_clean[:, 0], reduced_data_clean[:, 1], c=clean_clusters, cmap='viridis', edgecolor='k')
  # plt.title('PCA of Clusters')
  # plt.xlabel('Principal Component 1')
  # plt.ylabel('Principal Component 2')
  # plt.grid(True)
  # plt.show()

  # Step 4: Line Plot of Averaged Columns per Cluster
  plt.figure(figsize=(14, 7))
  #plt.yscale('log')
  plt.grid(axis='x', linestyle='--', alpha=0.5)  # Keeping only x-axis gridlines

  # Transpose clean_data back to the original orientation for plotting
  clean_data_T = clean_data.T

  # Calculate and plot the average timeseries for each cluster
  for cluster in np.unique(clean_clusters):
    # Identify columns in the cluster
    columns_in_cluster = clean_data_T.loc[:, clean_clusters == cluster]  
    cluster_average = columns_in_cluster.mean(axis=1)  
    # Apply a rolling average to the average timeseries
    rolling_avg_of_avg = cluster_average.rolling(window=window_size).mean().iloc[::take_every_nth_row]    
    x_values = np.linspace(-fruition_window, fruition_window, num=len(rolling_avg_of_avg))
    plt.plot(x_values, rolling_avg_of_avg, label=f'Cluster {cluster + 1}')

  # Add labels and legend
  plt.title('Alpha Band Power (Avg) Centered Around Fruition Events')
  plt.xlabel('Time (centered at Fruitions)')
  plt.ylabel('Alpha Band Power')
  plt.legend(title='Cluster', loc='upper right')  
  plt.axvline(x=0, color='k', linestyle='--', label='Event Time')
  plt.grid(False)  
  plt.show()

  # Step 5: Individual Plots for Each Cluster
  

  for cluster in np.unique(clean_clusters):
    # Identify columns in the cluster
    columns_in_cluster = clean_data_T.loc[:, clean_clusters == cluster]

    plt.figure(figsize=(14, 7))
    plt.grid(axis='x', linestyle='--', alpha=0.5)  # Keeping only x-axis gridlines
    #plt.yscale('log')
    
    # Plotting all raw data rows in the cluster
    for col in columns_in_cluster.columns:
        rolling_avg = columns_in_cluster[col].rolling(window=window_size).mean().iloc[::take_every_nth_row]
        plt.plot(x_values, rolling_avg, alpha=0.5, color='lightgrey')
    
    # Calculate and plot the average timeseries
    cluster_average = columns_in_cluster.mean(axis=1)
    rolling_avg_of_avg = cluster_average.rolling(window=window_size).mean()
    plt.plot(x_values, rolling_avg_of_avg, label=f'Average Line', color='black', linewidth=2)

    # Add labels and legend
    plt.title(f'All Fruition Events for Cluster {cluster + 1}')
    plt.xlabel('Time (centered at Fruition Event)')
    plt.ylabel('Alpha Power')
    #plt.legend(title='Cluster', loc='upper right')
    plt.axvline(x=0, color='k', linestyle='--', label='Event Time')    
    plt.grid(False)  
    plt.show()



