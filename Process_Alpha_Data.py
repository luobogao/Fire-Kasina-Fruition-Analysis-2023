# Input: Requires a folder which contains every sub-folder with each meditation data, including a .VHDR, .EEG file and also the 'timestamps.csv' file

# Alpha power for all bands, PLUS the variance on Fp1 for fruition detection
# Looks for a file 'timestamps.csv' and joins the notes at the right second (file must have 'seconds' and 'label' columns)
# Estimates the fruition event based on highest variance that comes within 30 preceding rows of noted fruition
# Updates the note at that point to say "FRUITION-CALC"

import os
import mne
import pandas as pd
import numpy as np
import sys
from mne.time_frequency import psd_array_multitaper

max_seconds_before = 50

def mmss_to_seconds(mmss_str):
    """Convert a string in mm:ss format to seconds."""
    minutes, seconds = map(int, mmss_str.split(':'))
    return minutes * 60 + seconds

def compute_secondwise_variance(data_series, fs=500):
    chunks = [data_series[i:i+fs] for i in range(0, len(data_series), fs)]
    return [chunk.var() for chunk in chunks]

def process_eeg_data(folder_path, vhdr_file):
    print ("Loading "  + folder_path)
    vhdr_file_path = os.path.join(folder_path, vhdr_file)
    timestamps_file_path = os.path.join(folder_path, "timestamps.csv")
    if not os.path.exists(timestamps_file_path):
        print(f"Skipping folder {folder_path} as it does not contain timestamps.csv.")
        return
    

    # Load the VHDR file using MNE
    raw = mne.io.read_raw_brainvision(vhdr_file_path, preload=True)
    raw.set_eeg_reference(ref_channels=['A2'])

    # Epoching the re-referenced data into 1-second epochs
    events = mne.make_fixed_length_events(raw, duration=1.0)
    epochs = mne.Epochs(raw, events, tmin=0, tmax=1, baseline=None, detrend=1, preload=True)

    # Extracting the EEG data as a NumPy array
    data = epochs.get_data(picks='eeg')

    psd, freqs = psd_array_multitaper(data, sfreq=epochs.info['sfreq'], fmin=8, fmax=12, verbose=False)

    # Averaging the PSD across the frequency bins to get power
    alpha_power = psd.mean(axis=-1).squeeze()
    alpha_power = np.round(alpha_power * 1e13, 1) 

    n_channels = alpha_power.shape[1]
    eeg_ch_names = epochs.ch_names[:n_channels]

    alpha_power_df = pd.DataFrame(data=alpha_power, columns=eeg_ch_names)
    alpha_power_df['Time (s)'] = np.arange(1, len(alpha_power_df) + 1)

    fp1_variance = compute_secondwise_variance(raw.get_data(picks='Fp1').squeeze())
    fp1_variance = np.array(fp1_variance)
    fp1_variance = np.round(fp1_variance * 1e9, 3)
    alpha_power_df['Var Fp1'] = fp1_variance[:len(alpha_power_df)]

    alpha_power_df = alpha_power_df[['Time (s)', 'Var Fp1'] + eeg_ch_names]

    timestamps_df = pd.read_csv(timestamps_file_path)
    timestamps_df['time'] = timestamps_df['time'].apply(mmss_to_seconds)
    timestamps_df['time'] = timestamps_df['time'].astype(int)
    alpha_power_df = pd.merge(alpha_power_df, timestamps_df, how='left', left_on='Time (s)', right_on='time')
    alpha_power_df = alpha_power_df.drop(columns=['time'])
    alpha_power_df = alpha_power_df.rename(columns={'label': 'notes'})

    for index, row in alpha_power_df.iterrows():
        if 'fruition' in str(row['notes']).lower():
            start_idx = max(0, index - max_seconds_before)
            end_idx = index
            max_var_idx = alpha_power_df['Var Fp1'][start_idx:end_idx].idxmax()
            alpha_power_df.at[max_var_idx, 'notes'] = "FRUITION-CALC"

    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Pre-Processed Alpha CSVs")
    os.makedirs(output_dir, exist_ok=True)
    csv_file_name = os.path.splitext(vhdr_file)[0] + ".csv"
    csv_file_path = os.path.join(output_dir, csv_file_name)
    alpha_power_df.to_csv(csv_file_path, index=False)
    print(f"Alpha power timeseries data saved to: {csv_file_path}")

def search_and_process(root_dir):
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for file in filenames:
            if file.endswith('.vhdr'):
                process_eeg_data(dirpath, file)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Please provide the root directory path to search for VHDR files.")
    else:
        search_and_process(sys.argv[1])
