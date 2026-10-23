"use strict";
const $ = (id) => document.getElementById(id);
const app = $("app");
const storageKey = "traffic-team.session.v1";
let state = null,
  config,
  busy = false,
  editing = null,
  file = null,
  preview = null,
  job = null,
  timer = null;
const errors = {
  revision_conflict:
    "다른 창에서 답변이 바뀌었습니다. 최신 상태를 불러왔으니 다시 선택해 주세요.",
  question_mismatch: "질문이 변경됐습니다. 현재 질문을 다시 확인해 주세요.",
  storage_unavailable: "저장 공간에 접근하지 못했습니다.",
  uncollected_branch: "아직 준비되지 않은 선택지입니다.",
};
function element(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
}
function button(text, callback, cls = "primary") {
  const b = element("button", text, cls);
  b.type = "button";
  b.disabled = busy;
  b.onclick = callback;
  return b;
}
function notify(text = "") {
  $("notice").textContent = text;
  $("notice").hidden = !text;
}
async function api(url, method = "GET", body) {
  const r = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json();
  if (!r.ok) {
    const e = new Error(
      data.error?.message ||
        errors[data.error?.code] ||
        `요청을 처리하지 못했습니다 (${r.status}).`,
    );
    e.status = r.status;
    throw e;
  }
  return data;
}
function remember() {
  try {
    localStorage.setItem(
      storageKey,
      JSON.stringify({ session: state.session_id, job: job?.job_id || null }),
    );
  } catch {}
}
function clearVideo() {
  clearTimeout(timer);
  timer = null;
  job = null;
  file = null;
  if (preview) URL.revokeObjectURL(preview);
  preview = null;
}
async function action(fn) {
  if (busy) return;
  busy = true;
  notify();
  render();
  try {
    await fn();
  } catch (e) {
    notify(e.message);
    if (e.status === 409 && state) {
      try {
        state = await api("/sessions/" + state.session_id);
        editing = null;
        clearVideo();
        remember();
      } catch {}
    }
  } finally {
    busy = false;
    render();
  }
}
async function start() {
  await action(async () => {
    const next = await api("/sessions", "POST", {
      question_schema_version: config.question_schema_version,
    });
    clearVideo();
    state = next;
    editing = null;
    remember();
  });
}
async function answer(option) {
  await action(async () => {
    if (editing) {
      const changed = await api(
        `/sessions/${state.session_id}/answers/${editing.question_id}`,
        "PUT",
        { selected_option_ids: [option], expected_revision: state.revision },
      );
      if (changed.changed) clearVideo();
      state = await api("/sessions/" + state.session_id);
    } else {
      state = await api(`/sessions/${state.session_id}/answers`, "POST", {
        question_id: state.current_question_id,
        selected_option_ids: [option],
        expected_revision: state.revision,
      });
    }
    editing = null;
    remember();
  });
}
function render() {
  app.replaceChildren();
  $("restart").hidden = !state;
  $("restart").disabled =
    busy || ["queued", "processing", "uploading"].includes(job?.status);
  const phase =
    !state || state.status !== "completed" || editing
      ? 0
      : job?.status === "completed"
        ? 2
        : 1;
  [...$("steps").children].forEach((n, i) =>
    n.classList.toggle("active", phase === i),
  );
  $("phase").textContent = [
    "01 / 사고 상황 선택",
    "02 / 영상 첨부",
    "03 / 감지 장면 확인",
  ][phase];
  if (!state) {
    const c = element("section", undefined, "card");
    c.append(
      element("span", "사고 상황 기록 시작", "intro-icon"),
      element("h2", "사고 상황을 하나씩 확인할게요."),
      element(
        "p",
        "기억나는 내용부터 선택해 주세요. 답변은 자동으로 저장되며, 나중에 수정할 수 있어요.",
        "muted",
      ),
      button(busy ? "준비 중…" : "사고 상황 입력 시작", start),
      element(
        "p",
        "현재 차대차 문답을 지원합니다. 차량 A·B와 내 차의 대응은 아직 확정되지 않았습니다.",
        "hint",
      ),
    );
    app.append(c);
    return;
  }
  if (state.history.length) {
    const d = element("details", undefined, "history");
    d.append(
      element(
        "summary",
        `지금까지 선택한 답변 ${state.history.length}개 · 확인 / 수정`,
      ),
    );
    for (const h of state.history) {
      const row = element("div", undefined, "history-item");
      row.append(
        element("p", h.question_snapshot.text),
        element(
          "strong",
          h.selected_option_snapshots.map((o) => o.label).join(", "),
        ),
      );
      const edit = button(
        "이 답변 수정",
        () => {
          editing = h.question_snapshot;
          notify();
          render();
        },
        "text-button",
      );
      edit.disabled =
        busy || ["queued", "processing", "uploading"].includes(job?.status);
      row.append(edit);
      d.append(row);
    }
    app.append(d);
  }
  const c = element("section", undefined, "card");
  app.append(c);
  const q = editing || state.current_question;
  if (q) {
    c.append(
      element(
        "span",
        editing ? "이전 답변 수정" : `질문 ${state.history.length + 1}`,
        "intro-icon",
      ),
      element("h2", q.text),
    );
    if (editing)
      c.append(
        element(
          "p",
          "다른 선택지로 변경하면 이후 답변과 기존 영상 결과를 다시 확인해야 합니다.",
          "warning",
        ),
      );
    const choices = element("div", undefined, "choices");
    for (const o of q.options) {
      const b = button(
        o.label + (o.collection_status !== "verified" ? " · 준비 중" : ""),
        () => answer(o.option_id),
        "choice",
      );
      b.disabled = busy || o.collection_status !== "verified";
      choices.append(b);
    }
    c.append(choices);
    if (editing)
      c.append(
        button(
          "수정 취소",
          () => {
            editing = null;
            render();
          },
          "text-button",
        ),
      );
    return;
  }
  if (job?.status === "completed") {
    c.append(
      element("span", "차량 감지 완료", "intro-icon"),
      element("h2", "영상에서 차량을 찾았어요."),
      element("p", job.message, "warning"),
      element(
        "p",
        `${job.timestamp_seconds.toFixed(2)}초 장면 · 차량 ${job.detections.length}개`,
        "muted",
      ),
    );
    const img = element("img", undefined, "result-image");
    img.src = `/video-jobs/${job.job_id}/detected.jpg`;
    img.alt = "차량 위치에 네모 표시를 한 영상 추출 사진";
    c.append(img);
    for (const d of job.detections)
      c.append(
        element(
          "span",
          `${{ car: "승용차", motorcycle: "오토바이", bus: "버스", truck: "트럭" }[d.label] || d.label} · 모델 점수 ${Math.round(d.confidence * 100)}%`,
          "pill",
        ),
      );
    const links = element("div", undefined, "actions");
    for (const [name, label] of [
      ["detected", "네모 표시 사진 저장"],
      ["original", "원본 사진 저장"],
    ]) {
      const a = element("a", label, "secondary");
      a.href = `/video-jobs/${job.job_id}/${name}.jpg`;
      a.download = `${name}.jpg`;
      links.append(a);
    }
    c.append(
      links,
      element(
        "p",
        "모델 점수는 인식 결과에 대한 점수이며 사고 확률이나 과실비율이 아닙니다.",
        "hint",
      ),
      button(
        "다른 영상 분석",
        () => {
          clearVideo();
          remember();
          render();
        },
        "text-button",
      ),
    );
    return;
  }
  c.append(
    element("span", "질문 완료", "intro-icon"),
    element("h2", "영상을 첨부해 주세요."),
    element(
      "p",
      "승용차·오토바이·버스·트럭을 찾아 사진으로 저장합니다. 사고 순간을 판별하는 기능은 아닙니다.",
      "muted",
    ),
  );
  if (job && ["queued", "processing", "uploading"].includes(job.status)) {
    c.append(element("p", job.message));
    const p = element("progress");
    p.max = 100;
    p.value = job.progress;
    c.append(
      p,
      element(
        "p",
        job.status === "uploading"
          ? `전송 ${job.progress}%`
          : `검사 ${job.progress}% · 이 화면에서 기다려 주세요.`,
        "hint",
      ),
    );
    return;
  }
  if (job) c.append(element("p", job.message, "warning"));
  const label = element("label", undefined, "upload");
  label.append(element("span", "분석할 영상 선택"));
  const input = element("input");
  input.type = "file";
  input.accept = ".mp4,.mov,.avi,.mkv,.webm";
  input.disabled = busy;
  input.onchange = () => {
    const picked = input.files[0];
    if (!picked) return;
    if (picked.size === 0 || picked.size > config.max_upload_bytes) {
      notify("0바이트 초과, 200MB 이하의 영상을 선택해 주세요.");
      return;
    }
    notify();
    if (preview) URL.revokeObjectURL(preview);
    file = picked;
    preview = URL.createObjectURL(file);
    job = null;
    render();
  };
  label.append(input);
  c.append(
    label,
    element(
      "p",
      "최대 200MB · 2분 · 4K / MP4(H.264) 권장. 약 0.5초 간격으로 검사합니다.",
      "hint",
    ),
  );
  if (file) {
    c.append(
      element(
        "p",
        `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)}MB`,
        "muted",
      ),
    );
    const video = element("video");
    video.controls = true;
    video.src = preview;
    video.preload = "metadata";
    c.append(video);
  }
  if (!config.model_ready)
    c.append(
      element(
        "p",
        "서버에 YOLO 모델이 없습니다. README의 모델 준비 절차를 진행해 주세요.",
        "warning",
      ),
    );
  const upload = button("차량 인식하고 사진 저장", uploadVideo);
  upload.disabled = busy || !file || !config.model_ready;
  const uploadActions = element("div", undefined, "actions");
  uploadActions.append(upload);
  c.append(uploadActions);
  c.append(
    element(
      "p",
      "관련 법규·판례와 과실비율 해설은 팀의 별도 기능과 연결할 예정입니다.",
      "hint",
    ),
  );
}
function uploadVideo() {
  if (!file || busy) return;
  busy = true;
  notify();
  job = {
    status: "uploading",
    progress: 0,
    message: "영상을 전송하고 있습니다.",
  };
  render();
  const xhr = new XMLHttpRequest();
  const query = new URLSearchParams({
    session_id: state.session_id,
    revision: state.revision,
    filename: file.name,
  });
  xhr.open("POST", "/video-jobs?" + query);
  xhr.setRequestHeader("Content-Type", "application/octet-stream");
  xhr.timeout = 120000;
  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) {
      job.progress = Math.round((e.loaded / e.total) * 100);
      render();
    }
  };
  const failed = (message) => {
    busy = false;
    job = null;
    notify(message);
    render();
  };
  xhr.onerror = () => failed("서버 연결이 끊겼습니다. 다시 시도해 주세요.");
  xhr.ontimeout = () =>
    failed("전송 시간이 초과됐습니다. 더 짧은 영상을 선택해 주세요.");
  xhr.onload = () => {
    let data;
    try {
      data = JSON.parse(xhr.responseText);
    } catch {
      return failed("서버 응답을 읽지 못했습니다.");
    }
    busy = false;
    if (xhr.status !== 202)
      return failed(data.error?.message || "영상 업로드에 실패했습니다.");
    job = data;
    remember();
    render();
    poll();
  };
  xhr.send(file);
}
async function poll() {
  clearTimeout(timer);
  if (!job?.job_id) return;
  try {
    job = await api("/video-jobs/" + job.job_id);
    remember();
    render();
    if (["queued", "processing", "uploading"].includes(job.status))
      timer = setTimeout(poll, 1000);
  } catch (e) {
    if (e.status === 409) {
      clearVideo();
      remember();
    }
    notify(e.message);
    render();
    const retry = button("상태 다시 확인", poll, "secondary");
    app.append(retry);
  }
}
$("restart").onclick = () => {
  if (confirm("현재 기록은 서버에 보관하고 새 대화를 시작할까요?")) start();
};
(async () => {
  try {
    config = await api("/app-config");
    let saved;
    try {
      saved = JSON.parse(localStorage.getItem(storageKey));
    } catch {}
    if (saved?.session) {
      try {
        state = await api("/sessions/" + saved.session);
      } catch (e) {
        if (e.status !== 404) throw e;
        localStorage.removeItem(storageKey);
      }
      if (state && saved.job) {
        job = { job_id: saved.job };
        await poll();
      }
    }
    render();
  } catch (e) {
    notify("서버를 확인해 주세요. " + e.message);
    app.append(button("다시 연결", () => location.reload(), "secondary"));
  }
})();
