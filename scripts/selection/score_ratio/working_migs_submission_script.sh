#!/bin/bash

# Source the LSF configuration profile
source /admin/lsftest/conf/profile.lsf

# Disable core dumps
ulimit -c 0

# Define the path to your Python script
PYTHON_SCRIPT="./selection_score_ratio.py"

# Generate a timestamp for the current time
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")

# Define the base output directory for results
BASE_OUT_DIR="/data/chodera/retchinm/score_ratio"

# Create a new directory for this run with the timestamp
RUN_DIR="${BASE_OUT_DIR}/${TIMESTAMP}"
LOGS_DIR="${RUN_DIR}/logs"

# Make sure the new directories exist
mkdir -p "$RUN_DIR"
mkdir -p "$LOGS_DIR"

# Number of trials to run for each noise level
NUM_TRIALS=1

# Define specific score ratios
SCORE_RATIOS=(1 2 5 10 20 40)

# Run multiple trials for each batch size
for (( TRIAL=1; TRIAL<=NUM_TRIALS; TRIAL++ )); do
    # Run the python script several times in parallel for each batch size
    for SCORE_RATIO in "${SCORE_RATIOS[@]}"; do
        echo "Trial $TRIAL for score ratio $SCORE_RATIO"

        # Submit a bsub job to run the script in parallel instances
        bsub -q gpuqueue -n 4 -gpu "num=1:mig=1/1:aff=no" \
             -J drug-gym_${SCORE_RATIO}_${TRIAL} -R "rusage[mem=8] span[hosts=1]" -W 5:59 \
             -o "${LOGS_DIR}/temp_${SCORE_RATIO}_trial_${TRIAL}.stdout" \
             -eo "${LOGS_DIR}/temp_${SCORE_RATIO}_trial_${TRIAL}.stderr" \
             /usr/bin/sh /home/retchinm/chodera/drug-gym/scripts/selection/score_ratio/run_trial.sh $SCORE_RATIO $RUN_DIR
    done
    echo "Completed all trials for score ratio: $SCORE_RATIO"
done
echo "All trials completed."