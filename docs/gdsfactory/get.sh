#!/bin/bash

# Target configuration
BASE_URL="https://gdsfactory.github.io/gdsfactory/notebooks"
OUTPUT_DIR="gdsfactory_notebooks"
MAX_WORKERS=10

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo "Fetching notebook list from $BASE_URL..."

# Step 1: "Wildcard" via curl + regex parsing to grab links
# Fetches html, searches for files ending in .ipynb or .html, and strips the href formatting
LINKS=$(curl -s "$BASE_URL" | grep -oE 'href="[^"]+/"' | sed -E 's/href="([^"]+)"/\1/' | grep -vE '(^|/)\.\.?/$|^/$')

if [ -z "$LINKS" ]; then
    echo "No files found to download. Check if the index page changed."
    exit 1
fi

# Convert string list to an array and de-duplicate
MAPFILE_EXPECTED=()
readarray -t UNIQUE_LINKS < <(echo "$LINKS" | sort -u)
echo "Found ${#UNIQUE_LINKS[@]} files to download."

# Step 2: ThreadPool / Parallel Worker Execution Loop
current_jobs=0

for LINK in "${UNIQUE_LINKS[@]}"; do
    # Handle absolute vs relative URLs
    if [[ "$LINK" == http* ]]; then
        URL="$LINK"
    else
        URL="${BASE_URL}/${LINK#/}"
    fi

    FILENAME=$(basename "${URL%/}")

    # Launch curl download in the background (equivalent to a worker thread)
    echo "Curling: $FILENAME..."
    curl -s -L -o "$OUTPUT_DIR/$FILENAME" "$URL" &

    # Throttle control: Limit background jobs to MAX_WORKERS
    ((current_jobs++))
    if [ "$current_jobs" -ge "$MAX_WORKERS" ]; then
        wait -n # Wait for any single background job to finish before launching the next
        ((current_jobs--))
    fi
done

# Wait for any remaining background downloads to wrap up
wait
echo "All downloads complete! Files saved in: $OUTPUT_DIR"
