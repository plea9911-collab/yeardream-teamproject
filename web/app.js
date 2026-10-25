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
  timer = null,
  accidentResult = null,
  resultLoading = false,
  resultError = "",
  resultRequest = 0;
let selected = null,
  selectedQuestion = null,
  imageMode = "detected";
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
  resultRequest += 1;
  accidentResult = null;
  resultLoading = false;
  resultError = "";
  job = null;
  file = null;
  if (preview) URL.revokeObjectURL(preview);
  preview = null;
}
function resultKey() {
  return state && job?.job_id
    ? `${state.session_id}:${state.revision}:${job.job_id}`
    : null;
}
function isFinishedJob() {
  return ["completed", "no_detection", "failed"].includes(job?.status);
}
async function loadAccidentResult(force = false) {
  const key = resultKey();
  if (!key || !isFinishedJob() || (accidentResult && !force) || resultLoading)
    return;
  const request = ++resultRequest;
  resultLoading = true;
  resultError = "";
  render();
  try {
    const data = await api(`/video-jobs/${job.job_id}/result`);
    if (request !== resultRequest || key !== resultKey()) return;
    accidentResult = data;
  } catch (e) {
    if (request !== resultRequest || key !== resultKey()) return;
    resultError = e.message;
  } finally {
    if (request === resultRequest && key === resultKey()) {
      resultLoading = false;
      render();
    }
  }
}
function safeSourceUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}
function appendReferences(container) {
  if (!isFinishedJob()) return;
  const section = element("section", undefined, "reference-results");
  section.append(element("h3", "사고 상황 결과"));
  if (resultLoading) {
    section.append(element("p", "사고 유형에 맞는 자료를 불러오는 중입니다.", "muted"));
  } else if (resultError) {
    section.append(
      element("p", resultError, "warning"),
      button("관련 자료 다시 확인", () => loadAccidentResult(true), "secondary"),
    );
  } else if (accidentResult) {
    const type = accidentResult.accident_type || accidentResult.summary;
    if (type) section.append(element("p", type, "muted"));
    appendFault(section, accidentResult.fault);
    const addGroup = (title, items, status, emptyMessage) => {
      const group = element("div", undefined, "reference-group");
      group.append(element("h4", title));
      if (!Array.isArray(items) || !items.length) {
        group.append(
          element(
            "p",
            status === "not_in_provided_pdf" ? emptyMessage : "관련 자료를 찾지 못했습니다.",
            "hint",
          ),
        );
      } else {
        for (const item of items) {
          const detail = element("details", undefined, "reference-item");
          const label = item.content?.split(/\r?\n/)[0] || title;
          detail.append(element("summary", label));
          const pages = Array.isArray(item.pdf_pages) ? item.pdf_pages.join(", ") : "";
          if (item.pdf_name || pages)
            detail.append(element("p", `${item.pdf_name || "PDF"}${pages ? ` · ${pages}쪽` : ""}`, "hint"));
          detail.append(element("p", item.content || "", "reference-content"));
          const source = safeSourceUrl(item.source_url);
          if (source) {
            const link = element("a", "원문 출처 열기", "reference-link");
            link.href = source;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            detail.append(link);
          }
          group.append(detail);
        }
      }
      section.append(group);
    };
    addGroup("법규", accidentResult.laws, accidentResult.law_status, "제공된 PDF에 해당 사고유형의 법규가 없어요.");
    addGroup("판례", accidentResult.precedents, accidentResult.precedent_status, "제공된 PDF에 해당 사고유형의 판례가 없어요.");
  } else {
    section.append(
      button("사고 상황 결과 확인", () => loadAccidentResult(true), "secondary"),
    );
  }
  container.append(section);
}
function appendFault(container, fault) {
  const group = element("div", undefined, "reference-group");
  group.append(element("h4", "유형별 기본 과실비율"));
  if (fault?.status === "found" && fault.ratio) {
    const stats = element("dl", undefined, "stats");
    for (const key of ["A", "B"])
      stats.append(element("dt", `자료의 차량 ${key}`), element("dd", `${fault.ratio[key]}%`));
    group.append(stats, element("p", "A/B는 협회 자료의 차량 구분입니다. 내 차량·상대 차량으로 지정한 결과는 아닙니다.", "hint"));
  } else {
    group.append(element("p", "기본 과실비율 자료를 확인하지 못했어요.", "hint"));
  }
  if (fault?.accident_situation)
    group.append(element("p", fault.accident_situation, "reference-content"));
  if (fault?.explanation) {
    group.append(element("h4", "기본 과실 해설"), element("p", fault.explanation, "reference-content"));
  }
  if (fault?.application_criteria) {
    const detail = element("details", undefined, "reference-item");
    detail.append(element("summary", "이 자료의 적용 조건"), element("p", fault.application_criteria, "reference-content"));
    group.append(detail);
  }
  const source = safeSourceUrl(fault?.source_url);
  if (source) {
    const link = element("a", "과실비율·해설 원문 출처", "reference-link");
    link.href = source;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    group.append(link);
  }
  group.append(element("p", "선택한 사고 유형에 해당하는 협회 저장 자료입니다.", "hint"));
  container.append(group);
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
    const heading = app.querySelector("h2");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
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
    selectedQuestion = null;
    selected = null;
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
    selectedQuestion = null;
    selected = null;
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
  [...$("steps").children].forEach((n, i) => {
    n.classList.toggle("active", phase === i);
    if (phase === i) n.setAttribute("aria-current", "step");
    else n.removeAttribute("aria-current");
  });
  $("phase").textContent = [
    "01 / 사고 상황 선택",
    "02 / 영상 첨부",
    "03 / 감지 장면 확인",
  ][phase];
  app.classList.toggle("result-layout", phase === 2);
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
    if (state.status === "completed" && !editing) d.open = !job;
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
      element(
        "p",
        "해당하는 상황을 하나 고른 뒤 다음으로 넘어가세요.",
        "muted",
      ),
    );
    if (editing)
      c.append(
        element(
          "p",
          "다른 선택지로 변경하면 이후 답변과 기존 영상 결과를 다시 확인해야 합니다.",
          "warning",
        ),
      );
    if (selectedQuestion !== q.question_id) {
      selectedQuestion = q.question_id;
      selected = editing
        ? state.history.find((h) => h.question_id === q.question_id)
            ?.selected_option_ids[0]
        : null;
    }
    const choices = element("div", undefined, "choices");
    choices.setAttribute("role", "radiogroup");
    choices.setAttribute("aria-label", "사고 상황 선택");
    const next = button(editing ? "답변 수정 완료" : "다음", () =>
      answer(selected),
    );
    next.disabled = busy || !selected;
    for (const o of q.options) {
      const label = element("label", undefined, "choice");
      const radio = element("input");
      radio.type = "radio";
      radio.name = "answer";
      radio.value = o.option_id;
      radio.checked = selected === o.option_id;
      radio.disabled = busy || o.collection_status !== "verified";
      label.classList.toggle("unavailable", radio.disabled && !busy);
      radio.onchange = () => {
        selected = o.option_id;
        next.disabled = busy;
      };
      const optionText = element("span", o.label);
      const explanations = {
        "같은 방향 진행차량 상호 간의 사고":
          "두 차가 같은 방향으로 가던 중 발생한 사고",
        "마주보는 방향 진행차량 상호 간의 사고":
          "두 차가 서로 마주 오는 방향에서 발생한 사고",
        "안전거리미확보로 인한 추돌사고":
          "뒤따르던 차가 앞차의 뒷부분을 들이받은 상황",
        "자동차 대 이륜차 특수유형": "자동차와 오토바이 사이의 사고 유형",
      };
      if (explanations[o.label])
        optionText.append(
          element("span", explanations[o.label], "option-help"),
        );
      label.append(radio, optionText);
      if (o.collection_status !== "verified")
        label.append(element("small", "준비 중"));
      choices.append(label);
    }
    const navigation = element("div", undefined, "actions");
    navigation.append(next);
    c.append(choices, navigation);
    if (editing)
      c.append(
        button(
          "수정 취소",
          () => {
            editing = null;
            selectedQuestion = null;
            render();
          },
          "text-button",
        ),
      );
    return;
  }
  if (job?.status === "completed") {
    c.classList.add("result-card");
    c.append(
      element("span", "영상 확인 완료", "intro-icon"),
      element("h2", "차량이 보이는 장면을 찾았어요."),
      element("p", "사진을 비교하고 필요한 장면을 저장하세요.", "muted"),
    );
    const workspace = element("div", undefined, "photo-workspace");
    const viewer = element("div", undefined, "viewer");
    const toolbar = element("div", undefined, "photo-toolbar");
    const modes = element("div", undefined, "segmented");
    modes.setAttribute("aria-label", "사진 표시 방식");
    const img = element("img", undefined, "result-image");
    const modeButtons = [];
    const update = () => {
      img.src = `/video-jobs/${job.job_id}/${imageMode}.jpg`;
      img.alt =
        imageMode === "detected"
          ? "차량 위치에 네모 표시를 한 사진"
          : "차량 표시 없는 같은 장면의 원본 사진";
      modeButtons.forEach(([mode, b]) =>
        b.setAttribute("aria-pressed", String(imageMode === mode)),
      );
    };
    for (const [mode, title] of [
      ["detected", "차량 표시"],
      ["original", "원본"],
    ]) {
      const b = button(
        title,
        () => {
          imageMode = mode;
          update();
        },
        "mode-button",
      );
      modeButtons.push([mode, b]);
      modes.append(b);
    }
    const enlarge = button(
      "사진 확대 ↗",
      () => openPhoto(enlarge),
      "text-button",
    );
    toolbar.append(modes, enlarge);
    update();
    viewer.append(
      toolbar,
      img,
      element("p", "같은 시점의 원본과 차량 표시 사진입니다.", "image-caption"),
    );
    const info = element("aside", undefined, "result-info");
    info.append(element("h3", "장면 정보"));
    const stats = element("dl", undefined, "stats");
    for (const [key, value] of [
      ["영상 시점", `${job.timestamp_seconds.toFixed(2)}초`],
      ["감지된 차량", `${job.detections.length}대`],
    ]) {
      stats.append(element("dt", key), element("dd", value));
    }
    info.append(
      stats,
      element(
        "p",
        "차량이 처음 감지된 장면입니다. 충돌 순간이나 과실비율을 판단한 결과는 아닙니다.",
        "result-note",
      ),
    );
    for (const [name, title] of [
      ["detected", "차량 표시 사진 저장"],
      ["original", "원본 사진 저장"],
    ]) {
      const link = element(
        "a",
        title,
        name === "detected" ? "primary" : "secondary",
      );
      link.href = `/video-jobs/${job.job_id}/${name}.jpg`;
      link.download = `${name}.jpg`;
      info.append(link);
    }
    const technical = element("details", undefined, "technical");
    technical.append(element("summary", "인식 정보 자세히 보기"));
    for (const d of job.detections)
      technical.append(
        element(
          "p",
          `${{ car: "승용차", motorcycle: "오토바이", bus: "버스", truck: "트럭" }[d.label] || d.label} · 모델 점수 ${Math.round(d.confidence * 100)}%`,
        ),
      );
    technical.append(
      element(
        "p",
        "모델 점수는 인식에 대한 점수이며 사고 확률이나 과실비율이 아닙니다.",
        "hint",
      ),
    );
    info.append(
      technical,
      button(
        "다른 영상 선택",
        () => {
          clearVideo();
          remember();
          render();
        },
        "text-button",
      ),
    );
    workspace.append(viewer, info);
    c.append(workspace);
    appendReferences(c);
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
    const status = element("p", job.message);
    status.setAttribute("role", "status");
    c.append(status);
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
  appendReferences(c);
  const label = element("label", undefined, "upload");
  label.append(
    element("strong", file ? "다른 영상으로 변경" : "분석할 영상 선택"),
    element("span", "블랙박스 또는 CCTV 파일을 불러오세요.", "muted"),
  );
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
    resultRequest += 1;
    accidentResult = null;
    resultLoading = false;
    resultError = "";
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
function openPhoto(trigger) {
  const dialog = element("dialog", undefined, "photo-dialog");
  dialog.setAttribute("aria-label", "사진 확대 보기");
  const toolbar = element("div", undefined, "zoom-toolbar");
  const title = element("strong", "사진 확대 보기");
  const stage = element("div", undefined, "zoom-stage");
  stage.tabIndex = 0;
  stage.setAttribute("aria-label", "확대된 사진. 방향키로 이동할 수 있습니다.");
  const image = element("img");
  let zoom = 1,
    mode = imageMode;
  const scale = element("span", "화면에 맞춤", "zoom-scale");
  const update = () => {
    image.src = `/video-jobs/${job.job_id}/${mode}.jpg`;
    image.alt =
      mode === "original" ? "확대한 원본 사진" : "확대한 차량 표시 사진";
    const fit = () => {
      if (!image.naturalWidth || !stage.clientHeight) return;
      const ratio = Math.min(
        (stage.clientWidth - 32) / image.naturalWidth,
        (stage.clientHeight - 32) / image.naturalHeight,
      );
      image.style.width = `${image.naturalWidth * ratio * zoom}px`;
      image.style.height = `${image.naturalHeight * ratio * zoom}px`;
    };
    image.onload = fit;
    requestAnimationFrame(fit);
    scale.textContent = zoom === 1 ? "화면에 맞춤" : `확대 ${zoom}배`;
  };
  const toggle = button(
    mode === "detected" ? "원본 보기" : "차량 표시 보기",
    () => {
      mode = mode === "detected" ? "original" : "detected";
      toggle.textContent = mode === "detected" ? "원본 보기" : "차량 표시 보기";
      update();
    },
    "secondary",
  );
  toolbar.append(
    title,
    toggle,
    button(
      "축소 −",
      () => {
        zoom = Math.max(1, zoom - 1);
        update();
      },
      "secondary",
    ),
    scale,
    button(
      "확대 +",
      () => {
        zoom = Math.min(4, zoom + 1);
        update();
      },
      "secondary",
    ),
    button("닫기 ✕", () => dialog.close(), "secondary"),
  );
  stage.append(image);
  dialog.append(toolbar, stage);
  dialog.addEventListener("close", () => {
    dialog.remove();
    trigger.focus();
  });
  dialog.addEventListener("click", (e) => {
    if (e.target === dialog) dialog.close();
  });
  document.body.append(dialog);
  dialog.showModal();
  update();
  const resize = () => update();
  window.addEventListener("resize", resize);
  dialog.addEventListener("close", () =>
    window.removeEventListener("resize", resize),
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
    else void loadAccidentResult();
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
