const API = window.location.origin;

document.getElementById("uploadBtn").addEventListener("click", async () => {
  const file = document.getElementById("videoFile").files[0];
  if (!file) return alert("Select a video file");

  const status = document.getElementById("status");
  const progress = document.getElementById("progress");
  status.textContent = "Uploading...";
  progress.hidden = false;

  const form = new FormData();
  form.append("file", file);
  const upload = await fetch(`${API}/api/videos/upload`, { method: "POST", body: form });
  const { video_id } = await upload.json();

  status.textContent = "Processing...";
  const proc = await fetch(`${API}/api/videos/${video_id}/process`, { method: "POST" });
  const { job_id } = await proc.json();

  const poll = setInterval(async () => {
    const res = await fetch(`${API}/api/jobs/${job_id}/status`);
    const job = await res.json();
    progress.value = (job.progress || 0) * 100;
    status.textContent = `${job.status} — ${job.fps?.toFixed(1) || 0} FPS — ${job.incidents || 0} incidents`;

    if (job.status === "completed" || job.status === "failed") {
      clearInterval(poll);
      if (job.annotated_path) {
        status.innerHTML += `<br><a href="${API}/api/output/${job_id}/annotated" style="color:#60a5fa">Download annotated video</a>`;
      }
      loadIncidents();
    }
  }, 2000);
});

async function loadIncidents() {
  const res = await fetch(`${API}/api/incidents`);
  const items = await res.json();
  const ul = document.getElementById("incidents");
  ul.innerHTML = items.map(i => `
    <li class="severity-${i.severity}">
      <strong>${i.severity.toUpperCase()}</strong> — score ${i.score.toFixed(2)} @ ${i.timestamp_sec.toFixed(1)}s
      <br><a href="${API}/api/incidents/${i.id}/clip" style="color:#60a5fa">View clip</a>
    </li>
  `).join("");
}

const es = new EventSource(`${API}/api/stream/alerts`);
es.onmessage = (e) => {
  const data = JSON.parse(e.data);
  const ul = document.getElementById("alerts");
  const li = document.createElement("li");
  li.textContent = `ALERT: ${data.severity} ${data.event_type} score=${data.score.toFixed(2)}`;
  ul.prepend(li);
};

loadIncidents();
