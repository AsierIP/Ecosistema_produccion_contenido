"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const icons = {
    play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 10 7-10 7z"/></svg>',
    pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14M16 5v14"/></svg>',
    external: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6M20 4 10 14M11 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-6"/></svg>',
    check: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>',
    alert: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v8M12 18h.01"/></svg>',
    dot: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3"/></svg>'
  };
  const stateNames = {
    blocked: ["Necesita atención", "blocked"],
    failed: ["Revisar incidencia", "error"],
    error: ["Revisar incidencia", "error"],
    paused: ["En pausa", "inactive"],
    disabled: ["Desactivada", "inactive"],
    stopped: ["Detenida", "inactive"],
    running: ["Produciendo", "active"],
    working: ["Produciendo", "active"],
    processing: ["Produciendo", "active"],
    generating: ["Generando", "active"],
    rendering: ["Montando", "active"],
    reviewing: ["Revisando", "active"],
    review_pending: ["Vídeo pendiente de revisión", "inactive"],
    publishing: ["Publicando", "active"],
    ready: ["Lista", "active"],
    idle: ["En espera", "inactive"],
    waiting: ["En espera", "inactive"],
    queued: ["En cola", "inactive"],
    scheduled: ["Programado en YouTube", "inactive"],
    scheduled: ["Programada", "inactive"],
    complete: ["Completada", "active"],
    completed: ["Completada", "active"],
    published: ["Publicado", "active"],
    accepted: ["Etapa revisada", "active"],
    uncertain: ["Revisar antes de continuar", "blocked"]
  };
  const stageNames = {
    planning: "Preparando el próximo contenido", plan: "Preparando el próximo contenido",
    research: "Investigando y contrastando el tema", editorial: "Preparando el guion",
    scripting: "Preparando el guion", script: "Preparando el guion",
    voice: "Generando la narración", tts: "Generando la narración", audio: "Preparando el audio",
    visuals: "Creando las imágenes", images: "Creando las imágenes", image: "Creando las imágenes",
    animation: "Dando movimiento a las escenas", motion: "Dando movimiento a las escenas",
    render: "Montando el vídeo", rendering: "Montando el vídeo", assembly: "Montando el vídeo",
    qa: "Revisando la calidad", quality: "Revisando la calidad", editorial_qa: "Revisando el contenido",
    audiovisual_qa: "Revisando imagen, voz y subtítulos", review: "Revisando el resultado",
    publish: "Publicando el vídeo", publishing: "Publicando el vídeo", upload: "Subiendo el vídeo",
    complete: "Producción completada", completed: "Producción completada", published: "Publicación verificada",
    creative: "Preparando el contenido y las escenas", metadata: "Preparando el título y la descripción",
    assets: "Preparando las imágenes y el audio", visual: "Preparando las escenas",
    release: "Comprobando la publicación", running: "Producción en curso",
    media_check: "Comprobando el vídeo terminado", cutout: "Preparando las capas de imagen",
    review_pending: "Montaje e inspección técnica terminados; falta la revisión editorial y audiovisual independiente",
    ambient: "Animando el ambiente de las escenas", queued: "Esperando su turno de producción",
    scheduled: "Esperando la hora de publicación para comprobar el acceso público",
    blocked: "Hay requisitos pendientes para continuar", paused: "La línea está en pausa",
    ready: "Preparada para la siguiente etapa", idle: "Esperando la próxima producción",
    failed: "La etapa necesita revisión", uncertain: "Revisando el estado de una etapa interrumpida",
    accepted: "Etapa terminada y revisada"
  };
  let status = null;
  let updating = false;
  let mutating = false;
  let connected = false;
  let lastRenderedLines = "";
  let lastRenderedActivity = "";
  let refreshTimer = null;
  let closedByUser = false;

  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const key = (value) => typeof value === "string" ? value.trim().toLowerCase().replace(/[ -]/g, "_") : "";
  const text = (value, fallback = "") => typeof value === "string" && value.trim() ? value.trim() : fallback;
  const errorText = (error) => error instanceof Error ? error.message : "No se pudo completar la acción.";
  const icon = (name, className) => {
    const element = node("span", className);
    element.innerHTML = icons[name] || icons.dot;
    return element;
  };
  const dot = (className = "") => node("span", `status-dot ${className}`.trim());
  const dateText = (value, includeDate = false) => {
    if (!value) return "";
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return "";
    const options = {hour: "2-digit", minute: "2-digit"};
    if (includeDate) Object.assign(options, {day: "2-digit", month: "2-digit"});
    return new Intl.DateTimeFormat("es-ES", options).format(date);
  };
  const safeVideoUrl = (value) => {
    if (typeof value !== "string" || !value.trim()) return null;
    try {
      if (value.startsWith("/")) {
        const local = new URL(value, window.location.origin);
        return local.origin === window.location.origin && local.pathname.startsWith("/api/media/") ? local.href : null;
      }
      const url = new URL(value);
      return ["https:", "http:"].includes(url.protocol) ? url.href : null;
    } catch { return null; }
  };

  async function request(path, body) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const options = {credentials: "same-origin", cache: "no-store", signal: controller.signal};
      if (body !== undefined) {
        if (!status?.csrf_token) throw new Error("Falta la conexión segura con Upro. Recarga el panel antes de continuar.");
        options.method = "POST";
        options.headers = {"Content-Type": "application/json", "X-Upro-Token": status.csrf_token};
        options.body = JSON.stringify(body);
      }
      const response = await fetch(path, options);
      let data = null;
      try { data = await response.json(); } catch { /* A response without JSON is handled below. */ }
      if (!response.ok) {
        if (response.status === 403) throw new Error("La sesión del panel ha cambiado. Recarga la página para continuar.");
        const detail = typeof data?.error === "string" ? data.error : typeof data?.message === "string" ? data.message : "";
        throw new Error(detail ? detail.slice(0, 350) : `Upro no pudo completar la solicitud (${response.status}).`);
      }
      return data;
    } catch (error) {
      if (error?.name === "AbortError") throw new Error("Upro está tardando en responder. El panel volverá a comprobar la conexión.");
      if (error instanceof TypeError) throw new Error("No se puede conectar con Upro. Comprueba que el programa sigue abierto en este PC.");
      throw error;
    } finally { clearTimeout(timeout); }
  }

  function setError(message) {
    $("error-banner").textContent = message;
    $("error-banner").hidden = !message;
  }

  function setConnected(value) {
    connected = value;
    const label = $("connection-status");
    label.replaceChildren(dot(value ? "" : "error"), document.createTextNode(value ? "Conectado a tu PC" : "Sin conexión"));
    $("sidebar-dot").className = `status-dot${value ? "" : " error"}`;
    $("sidebar-device").textContent = value ? "Funciona en este PC" : "Conexión interrumpida";
    $("activity-dot").className = `status-dot${value ? "" : " muted"}`;
    $("activity-live").textContent = value ? "Actualización automática" : "Sin actualizar";
    document.querySelector(".studio-overview").classList.toggle("is-offline", !value);
    updateControls();
  }

  function updateControls() {
    $("refresh-button").disabled = closedByUser || mutating || updating;
    $("pause-button").disabled = closedByUser || !connected || !status?.csrf_token || mutating;
    $("shutdown-button").disabled = closedByUser || !connected || !status?.csrf_token || mutating;
    document.querySelectorAll(".switch").forEach((button) => { button.disabled = closedByUser || button.dataset.locked === "true" || !connected || !status?.csrf_token || mutating; });
  }

  function lineState(line) {
    const state = stateNames[key(line.state)];
    if (state) return state;
    if (line.enabled === false) return stateNames.disabled;
    if (Array.isArray(line.blockers) && line.blockers.length) return stateNames.blocked;
    return [text(line.state, "Estado pendiente"), "unknown"];
  }

  function initials(name) {
    const words = name.replace(/[^\p{L}\p{N}\s]/gu, "").trim().split(/\s+/).filter(Boolean);
    return (words.length > 1 ? words[0][0] + words[1][0] : (words[0] || "U").slice(0, 2)).toLocaleUpperCase("es-ES");
  }

  function blockerText(blocker) {
    if (typeof blocker === "string") return blocker;
    if (blocker && typeof blocker === "object") return text(blocker.message || blocker.description || blocker.reason || blocker.code, "Hay un requisito pendiente de revisión.");
    return "Hay un requisito pendiente de revisión.";
  }

  function renderLine(line, index) {
    const name = text(line.name, "Línea sin nombre");
    const article = node("article", "line-card");
    article.dataset.tone = ["cyan", "amber", "mint"][index % 3];
    const header = node("div", "line-card-top");
    header.append(node("span", "channel-icon", initials(name)));
    const title = node("div", "line-title");
    title.append(node("h3", "", name), node("p", "", "LÍNEA DE PRODUCCIÓN"));
    header.append(title);
    const toggle = node("div", "line-toggle");
    toggle.append(node("span", "", line.enabled === true ? "Activada" : "Desactivada"));
    const button = node("button", "switch");
    button.type = "button";
    button.setAttribute("role", "switch");
    button.setAttribute("aria-label", `Activar la línea ${name}`);
    button.setAttribute("aria-checked", String(line.enabled === true));
    button.dataset.lineId = String(line.id);
    button.dataset.locked = String(line.locked === true);
    button.disabled = line.locked === true || !status?.csrf_token || mutating;
    if (line.locked === true) {
      const reason = text(line.locked_reason || line.reason, Array.isArray(line.blockers) && line.blockers.length ? blockerText(line.blockers[0]) : "Esta línea está pausada por su configuración.");
      button.title = reason;
      button.setAttribute("aria-label", `${name}: ${reason}`);
      button.classList.add("switch-locked");
    }
    button.append(node("span"));
    toggle.append(button);
    header.append(toggle);
    article.append(header);

    const body = node("div", "line-body");
    const [label, type] = lineState(line);
    const statusRow = node("div", "line-status");
    const pill = node("span", `state-pill ${type}`);
    pill.append(dot(), document.createTextNode(label));
    statusRow.append(pill);
    const progress = typeof line.progress === "number" && Number.isFinite(line.progress) ? Math.max(0, Math.min(100, line.progress)) : null;
    if (progress !== null) statusRow.append(node("span", "progress-number", `${Math.round(progress)} %`));
    body.append(statusRow);
    let stage = stageNames[key(line.stage)] || text(line.stage);
    if (!stage) stage = line.enabled === false ? "Activa esta línea cuando quieras ponerla en marcha." : type === "blocked" ? "La producción espera a que se resuelvan estos requisitos." : "Sin una etapa de producción en curso.";
    if (line.locked === true && (!Array.isArray(line.blockers) || !line.blockers.length)) stage = text(line.locked_reason || line.reason, "Esta línea está pausada por su configuración.");
    body.append(node("p", "line-stage", stage));
    if (progress !== null) {
      const track = node("div", "progress-track");
      track.setAttribute("role", "progressbar");
      track.setAttribute("aria-label", `Avance de ${name}`);
      track.setAttribute("aria-valuenow", String(Math.round(progress)));
      track.setAttribute("aria-valuemin", "0");
      track.setAttribute("aria-valuemax", "100");
      const fill = node("div", "progress-fill");
      fill.style.width = `${progress}%`;
      track.append(fill);
      body.append(track);
    }
    if (Array.isArray(line.blockers) && line.blockers.length) {
      const blockers = node("ul", "line-blockers");
      line.blockers.forEach((blocker) => blockers.append(node("li", "", blockerText(blocker))));
      body.append(blockers);
    }
    if (Array.isArray(line.activation_blockers) && line.activation_blockers.length) {
      const details = node("details", "line-activation");
      details.append(node("summary", "", "Producción diaria autónoma: requisitos pendientes"));
      const requirements = node("ul", "line-blockers");
      line.activation_blockers.forEach((item) => requirements.append(node("li", "", blockerText(item))));
      details.append(requirements);
      body.append(details);
    }
    article.append(body);

    const footer = node("div", "line-footer");
    footer.append(icon("play", "video-icon"));
    const videoInfo = node("div", "video-info");
    const video = line.last_video && typeof line.last_video === "object" ? line.last_video : null;
    videoInfo.append(node("span", "eyebrow", "ÚLTIMO VÍDEO"));
    videoInfo.append(node("span", "video-title", video ? text(video.title, "Vídeo terminado") : "Aún no hay un vídeo registrado"));
    if (text(video?.status)) videoInfo.append(node("p", "video-note", text(video.status)));
    const videoUrl = safeVideoUrl(video?.url);
    if (video?.local_available && !videoUrl) videoInfo.append(node("p", "video-note", "Disponible en este PC"));
    footer.append(videoInfo);
    if (videoUrl) {
      const link = node("a", "video-link");
      link.href = videoUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.setAttribute("aria-label", `Ver ${text(video.title, "el último vídeo de " + name)} (abre una pestaña)`);
      link.append(icon("external"));
      footer.append(link);
    }
    article.append(footer);
    return article;
  }

  function renderActivity(items) {
    const signature = JSON.stringify(items);
    if (signature === lastRenderedActivity) return;
    lastRenderedActivity = signature;
    const list = $("activity-list");
    list.replaceChildren();
    if (!items.length) {
      list.append(node("li", "activity-empty", "Todavía no hay actividad registrada. Los avances aparecerán aquí."));
      return;
    }
    items.slice(0, 12).forEach((item) => {
      const entry = typeof item === "string" ? {message: item} : item || {};
      const level = key(entry.level || entry.status || entry.type);
      const warning = ["warning", "warn", "blocked"].includes(level);
      const failed = ["error", "failed"].includes(level);
      const element = node("li", "activity-item");
      element.append(icon(warning || failed ? "alert" : ["success", "complete", "completed", "published"].includes(level) ? "check" : "dot", `activity-symbol${failed ? " error" : warning ? " warning" : ""}`));
      const content = node("div", "activity-content");
      content.append(node("p", "activity-message", text(entry.message || entry.text || entry.title || entry.event, "Actualización de producción")));
      const detail = text(entry.detail || entry.description || entry.line_name || entry.channel_name);
      if (detail) content.append(node("p", "activity-detail", detail));
      element.append(content);
      const rawTime = entry.timestamp || entry.at || entry.created_at || entry.time;
      const formatted = dateText(rawTime, true);
      if (formatted) {
        const time = node("time", "activity-time", formatted);
        time.dateTime = new Date(rawTime).toISOString();
        element.append(time);
      }
      list.append(element);
    });
  }

  function render(data) {
    status = data;
    const lines = data.lines;
    const enabled = lines.filter((line) => line.enabled === true).length;
    const blocked = lines.filter((line) => line.enabled === true && (lineState(line)[1] === "blocked" || lineState(line)[1] === "error" || (Array.isArray(line.blockers) && line.blockers.length))).length;
    $("line-count").textContent = String(lines.length);
    $("line-summary").textContent = `${enabled} ${enabled === 1 ? "activada" : "activadas"}${blocked ? ` · ${blocked} ${blocked === 1 ? "necesita" : "necesitan"} atención` : ""}`;
    $("engine-title").textContent = data.paused ? "Estudio en pausa" : data.running ? "Estudio en marcha" : "Motor detenido";
    $("engine-detail").textContent = data.paused ? "Las líneas conservan su configuración para cuando reanudes." : data.running ? enabled ? "El motor coordina tus líneas y comprueba sus requisitos." : "Activa una línea para incorporarla a la producción." : "El motor no está produciendo en este momento.";
    document.querySelector(".studio-overview").classList.toggle("is-paused", !!data.paused);
    const pauseButton = $("pause-button");
    pauseButton.classList.toggle("resume", !!data.paused);
    pauseButton.replaceChildren(icon(data.paused ? "play" : "pause"), node("span", "", data.paused ? "Reanudar estudio" : "Pausar todas"));
    const gpuKnown = typeof data.resources?.gpu_busy === "boolean";
    $("gpu-status").textContent = gpuKnown ? data.resources.gpu_busy ? "GPU trabajando" : "GPU disponible" : "GPU: estado pendiente";
    $("gpu-dot").className = `status-dot${gpuKnown ? data.resources.gpu_busy ? " amber" : "" : " muted"}`;
    const executionNotice = text(data.execution_notice);
    $("execution-notice").textContent = executionNotice;
    $("execution-notice").hidden = !executionNotice;
    renderResources(data);
    const signature = JSON.stringify({lines, csrf: !!data.csrf_token});
    if (signature !== lastRenderedLines) {
      const focusedId = document.activeElement?.dataset?.lineId;
      lastRenderedLines = signature;
      $("lines").replaceChildren(...lines.map(renderLine));
      if (focusedId) Array.from(document.querySelectorAll(".switch")).find((button) => button.dataset.lineId === focusedId)?.focus({preventScroll: true});
    }
    $("lines").setAttribute("aria-busy", "false");
    $("empty-lines").hidden = lines.length > 0;
    $("lines").hidden = lines.length === 0;
    renderActivity(Array.isArray(data.activity) ? data.activity : []);
    const updated = dateText(data.updated_at, true);
    $("last-updated").textContent = updated ? `Última actualización: ${updated}` : "Estado recibido del motor";
    setConnected(true);
  }

  function renderResources(data) {
    const summary = $("resource-summary");
    summary.replaceChildren();
    const number = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0;
    const metric = (label, value) => {
      const element = node("span", "", label);
      element.append(node("strong", "", value));
      summary.append(element);
    };
    const resources = data.resources || {};
    if (number(resources.active_workers) && number(resources.max_workers)) metric("Tareas en marcha", `${resources.active_workers} / ${resources.max_workers}`);
    const usage = data.usage || {};
    const format = new Intl.NumberFormat("es-ES");
    if (number(usage.input_tokens) && number(usage.output_tokens)) metric("Tokens registrados", format.format(usage.input_tokens + usage.output_tokens));
    if (number(usage.cached_input_tokens)) metric("Tokens de entrada en caché", format.format(usage.cached_input_tokens));
    if (number(usage.runs)) metric("Ejecuciones registradas", format.format(usage.runs));
    if (summary.childElementCount) summary.append(node("span", "resource-hint", "Este panel se actualiza sin consumir tokens de agentes."));
    if (text(usage.note)) summary.append(node("p", "usage-note", text(usage.note)));
    summary.hidden = summary.childElementCount === 0;
  }

  async function refresh({clearError = true} = {}) {
    if (updating || closedByUser) return false;
    updating = true;
    updateControls();
    try {
      const data = await request("/api/status");
      if (closedByUser) return false;
      if (!data || !Array.isArray(data.lines) || typeof data.running !== "boolean" || typeof data.paused !== "boolean") throw new Error("El motor ha enviado un estado incompleto. No se han cambiado tus líneas.");
      render(data);
      if (clearError) setError("");
      return true;
    } catch (error) {
      if (closedByUser) return false;
      setConnected(false);
      setError(errorText(error));
      if (!status) {
        $("engine-title").textContent = "Conexión pendiente";
        $("engine-detail").textContent = "El panel necesita conectar con el motor local para mostrar tus líneas.";
        $("line-summary").textContent = "Esperando el estado del motor";
      }
      return false;
    } finally {
      updating = false;
      updateControls();
    }
  }

  async function mutate(path, body, announcement) {
    if (mutating || !status || closedByUser) return;
    mutating = true;
    updateControls();
    setError("");
    try {
      await request(path, body);
      const refreshed = await refresh();
      $("action-announcement").textContent = refreshed ? announcement : "La acción se ha enviado. Esperando la confirmación del motor.";
    } catch (error) {
      setError(errorText(error));
      $("action-announcement").textContent = "No se ha podido confirmar el cambio. Comprueba el estado del panel.";
      await refresh({clearError: false});
    } finally {
      mutating = false;
      updateControls();
    }
  }

  $("lines").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-line-id]");
    if (!button || button.disabled || !status) return;
    const line = status.lines.find((entry) => String(entry.id) === button.dataset.lineId);
    if (!line) return;
    const enabled = line.enabled !== true;
    mutate(`/api/lines/${encodeURIComponent(line.id)}`, {enabled}, `${line.name}: ${enabled ? "activada" : "desactivada"}.`);
  });
  $("pause-button").addEventListener("click", () => {
    if (!status) return;
    const paused = !status.paused;
    mutate("/api/control", {paused}, paused ? "Estudio en pausa." : "Estudio reanudado.");
  });
  $("refresh-button").addEventListener("click", () => {
    if (connected && status?.csrf_token) mutate("/api/tick", {}, "Estado de producción actualizado.");
    else refresh();
  });
  $("shutdown-button").addEventListener("click", async () => {
    if (mutating || !status || closedByUser) return;
    mutating = true;
    updateControls();
    setError("");
    try {
      const response = await request("/api/shutdown", {});
      closedByUser = true;
      clearTimeout(refreshTimer);
      const finishing = status.resources?.active_workers !== 0;
      document.body.classList.add("app-closed");
      setConnected(false);
      $("connection-status").replaceChildren(dot("muted"), document.createTextNode("Desconectado"));
      $("sidebar-dot").className = "status-dot muted";
      $("sidebar-device").textContent = "Upro se ha desconectado";
      $("engine-title").textContent = finishing ? "Cierre solicitado" : "Motor cerrado";
      $("engine-detail").textContent = text(response?.message, "El motor terminará las etapas en curso antes de cerrarse.") + " Puedes cerrar esta pestaña.";
      $("activity-live").textContent = "Último estado recibido";
      $("line-summary").textContent = "Último estado antes del cierre";
      $("gpu-status").textContent = "GPU: sin nuevas lecturas";
      $("gpu-dot").className = "status-dot muted";
      $("execution-notice").textContent = "Para volver a producir, abre Upro desde su acceso directo.";
      $("execution-notice").hidden = false;
      $("action-announcement").textContent = "Cierre solicitado. El motor terminará las etapas en curso antes de salir.";
      $("shutdown-button").querySelector("span").textContent = "Cierre solicitado";
    } catch (error) {
      setError(errorText(error));
      await refresh({clearError: false});
    } finally {
      mutating = false;
      updateControls();
    }
  });

  function scheduleRefresh() {
    clearTimeout(refreshTimer);
    if (document.hidden || closedByUser) return;
    refreshTimer = setTimeout(async () => {
      if (!mutating) await refresh();
      scheduleRefresh();
    }, 5000);
  }
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && !mutating && !closedByUser) refresh();
    scheduleRefresh();
  });
  window.addEventListener("online", () => { if (!mutating && !closedByUser) refresh(); });
  refresh().finally(scheduleRefresh);
})();
