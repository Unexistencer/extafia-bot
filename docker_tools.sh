set -euo pipefail

IMG_NAME="extafia:latest"
CTR_NAME="extafia"

# Optional local ADC file for non-GCE environments only
ADC_PATH="${ADC_PATH:-}"

menu() {
  echo "======================================"
  echo "Docker Tool List"
  echo "======================================"
  echo "1) Clean Docker"
  echo "2) Update extafia (build & run on python:3.12-slim)"
  echo "3) Exit"
  echo "======================================"
}

clean_all() {
  echo "Cleaning Docker..."
  docker container prune -f
  docker image prune -a -f
  docker volume prune -f
  docker builder prune -a -f
  echo "Success!"
  echo
  echo "Docker Storage:"
  df -h || true
  echo
}

update_extafia() {
  echo "Step 1: Cleaning dangling artifacts..."
  docker container prune -f
  docker image prune -a -f
  docker volume prune -f
  docker builder prune -a -f

  echo
  echo "Step 2: Pulling base image python:3.12-slim..."
  docker pull python:3.12-slim

  echo
  echo "Step 3: Rebuilding extafia image..."
  docker build -t "${IMG_NAME}" .

  echo
  echo "Step 4: Stop & remove old container if exists..."
  docker stop "${CTR_NAME}" 2>/dev/null || true
  docker rm   "${CTR_NAME}" 2>/dev/null || true

  echo
  echo "Step 5: Starting new extafia container..."
  LOG_DIR="$HOME/extafia/logs"
  mkdir -p "${LOG_DIR}"


  if [[ -z "${ADC_PATH}" || ! -f "${ADC_PATH}" ]]; then
  echo "INFO: No local ADC file mounted."
  echo "      Container will rely on runtime default credentials (e.g. GCE service account)."
  ADC_MOUNT=""
else
  ADC_MOUNT="-v ${ADC_PATH}:/secrets/adc.json:ro -e GOOGLE_APPLICATION_CREDENTIALS=/secrets/adc.json"
fi

  docker run -d \
    --name "${CTR_NAME}" \
    -v "${LOG_DIR}:/app/logs" \
    -e TZ=Asia/Tokyo \
    ${ADC_MOUNT} \
    "${IMG_NAME}"

    echo
    echo "Update success!"
    docker ps | grep "${CTR_NAME}" || true
    echo
}

while true; do
  menu
  read -r -p "Input (1/2/3): " choice
  case "$choice" in
    1) clean_all ;;
    2) update_extafia ;;
    3) echo "BYE!"; exit 0 ;;
    *) echo "Invalid."; ;;
  esac
done
