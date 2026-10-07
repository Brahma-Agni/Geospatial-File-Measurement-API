const form = document.querySelector("#upload-form");
const input = document.querySelector("#file-input");
const dropZone = document.querySelector("#drop-zone");
const fileRow = document.querySelector("#file-row");
const submitButton = document.querySelector("#submit-button");
const statusBox = document.querySelector("#status");
const errorBox = document.querySelector("#error");
const results = document.querySelector("#results");

const setText = (selector, value) => {
  document.querySelector(selector).textContent = value ?? "—";
};

const formatBytes = (bytes) => {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
};

const showError = (message) => {
  statusBox.hidden = true;
  errorBox.hidden = false;
  setText("#error-message", message);
  submitButton.disabled = !input.files.length;
};

const apiError = async (response) => {
  try {
    const body = await response.json();
    return body.error?.message || `Request failed with status ${response.status}.`;
  } catch {
    return `Request failed with status ${response.status}.`;
  }
};

const chooseFile = (file) => {
  errorBox.hidden = true;
  results.hidden = true;
  if (!file) {
    fileRow.hidden = true;
    submitButton.disabled = true;
    return;
  }
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (!["kml", "zip"].includes(extension)) {
    input.value = "";
    showError("Choose a .kml file or a .zip containing one ESRI Shapefile.");
    return;
  }
  if (file.size > 4 * 1024 * 1024) {
    input.value = "";
    showError("The production upload limit is 4 MB.");
    return;
  }
  setText("#file-type", extension.toUpperCase());
  setText("#file-name", file.name);
  setText("#file-size", formatBytes(file.size));
  fileRow.hidden = false;
  submitButton.disabled = false;
};

const renderMeasurements = (data) => {
  const rows = document.querySelector("#measurement-rows");
  rows.replaceChildren();
  data.features.forEach((feature) => {
    const measurement = feature.measurement;
    const row = document.createElement("tr");
    const values = [
      `#${feature.feature_index + 1}`,
      feature.geometry_type,
      measurement?.type || "Not applicable",
      measurement?.value == null ? "—" : `${measurement.value.toLocaleString(undefined, { maximumFractionDigits: 3 })} ${measurement.unit}`,
    ];
    values.forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    });
    const statusCell = document.createElement("td");
    const badge = document.createElement("span");
    const state = measurement?.status || "SKIPPED";
    badge.className = `status-pill${state === "FAILED" ? " failed" : ""}`;
    badge.textContent = state;
    statusCell.append(badge);
    row.append(statusCell);
    rows.append(row);
  });
};

input.addEventListener("change", () => chooseFile(input.files[0]));
document.querySelector("#remove-file").addEventListener("click", () => {
  input.value = "";
  chooseFile(null);
});

["dragenter", "dragover"].forEach((eventName) => dropZone.addEventListener(eventName, (event) => {
  event.preventDefault();
  dropZone.classList.add("dragging");
}));
["dragleave", "drop"].forEach((eventName) => dropZone.addEventListener(eventName, (event) => {
  event.preventDefault();
  dropZone.classList.remove("dragging");
}));
dropZone.addEventListener("drop", (event) => {
  const file = event.dataTransfer.files[0];
  if (!file) return;
  const transfer = new DataTransfer();
  transfer.items.add(file);
  input.files = transfer.files;
  chooseFile(file);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!input.files[0]) return;
  errorBox.hidden = true;
  results.hidden = true;
  statusBox.hidden = false;
  submitButton.disabled = true;

  try {
    const payload = new FormData();
    payload.append("file", input.files[0]);
    const uploadResponse = await fetch("/api/files/", { method: "POST", body: payload });
    if (!uploadResponse.ok) throw new Error(await apiError(uploadResponse));
    const upload = await uploadResponse.json();

    const measurementResponse = await fetch(`/api/files/${upload.id}/measurements/?limit=100`);
    if (!measurementResponse.ok) throw new Error(await apiError(measurementResponse));
    const measurements = await measurementResponse.json();

    setText("#result-file", upload.filename);
    setText("#result-count", upload.feature_count.toLocaleString());
    setText("#source-crs", upload.source_crs);
    setText("#measurement-crs", upload.measurement_crs);
    renderMeasurements(measurements);
    setText("#result-note", upload.feature_count > measurements.features.length
      ? `Showing the first ${measurements.features.length} of ${upload.feature_count} features.`
      : `Processed file ID: ${upload.id}`);
    statusBox.hidden = true;
    results.hidden = false;
    results.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showError(error.message || "The file could not be processed.");
  }
});

document.querySelector("#new-upload").addEventListener("click", () => {
  form.reset();
  chooseFile(null);
  results.hidden = true;
  document.querySelector("#upload-title").scrollIntoView({ behavior: "smooth" });
});
