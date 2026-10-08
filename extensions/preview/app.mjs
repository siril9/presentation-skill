import { App, applyDocumentTheme, applyHostStyleVariables } from "@modelcontextprotocol/ext-apps";
import { OpenAIExtensions } from "@openai/mcp-extensions/app";
import { createElement, RefreshCw, Hammer, GitCompareArrows, Send, ImageOff, Check } from "lucide";
import "./app.css";

const TOOLS = {
  open: "presentation_open",
  slide: "presentation_slide",
  build: "presentation_build",
  audition: "presentation_audition",
  preview: "presentation_preview",
};
const PRESETS = ["lab-report", "editorial-minimal", "warm-terracotta"];
const imageTypes = new Set(["image/png", "image/jpeg", "image/webp"]);

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const string = (value, fallback = "") => typeof value === "string" ? value : fallback;
const label = (value, fallback = "") => typeof value === "string" || typeof value === "number" ? String(value) : fallback;
const displayIndex = (value) => Number.isInteger(value) && value >= 0 ? String(value + 1) : "?";
const text = (tag, className, value) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = value;
  return node;
};
const icon = (definition) => {
  const node = createElement(definition, { width: 18, height: 18, "aria-hidden": "true" });
  node.setAttribute("focusable", "false");
  return node;
};
const button = (title, definition, className = "icon-button") => {
  const node = document.createElement("button");
  node.type = "button";
  node.className = className;
  node.title = title;
  node.setAttribute("aria-label", title);
  node.append(icon(definition));
  return node;
};

export function checkedToolResult(result) {
  if (!isObject(result)) throw new Error("Tool returned no result.");
  if (result.isError) {
    const message = Array.isArray(result.content)
      ? result.content.filter((part) => part?.type === "text").map((part) => part.text).join(" ")
      : "";
    throw new Error(message || "Tool request failed.");
  }
  if (!isObject(result.structuredContent)) throw new Error("Tool returned no structured content.");
  return result.structuredContent;
}

export function imageFromResult(result) {
  const preview = result?._meta?.preview;
  if (!isObject(preview) || !imageTypes.has(preview.mimeType) || typeof preview.data !== "string") return null;
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(preview.data)) return null;
  return `data:${preview.mimeType};base64,${preview.data}`;
}

function issueLabel(issue) {
  if (typeof issue === "string") return issue;
  if (!isObject(issue)) return "Issue";
  return string(issue.message) || string(issue.summary) || string(issue.code) || "Issue";
}

function deckResult(data) {
  return isObject(data) && typeof data.deck_id === "string" && Array.isArray(data.slides);
}

function slideResult(data) {
  return isObject(data) && (isObject(data.slide) || isObject(data.source));
}

function setup() {
  const root = document.querySelector("#app") || document.body;
  root.classList.add("presentation-preview");
  const app = new App({ name: "Presentation Preview", version: "1.0.0" }, {}, { strict: true });
  const openai = new OpenAIExtensions(app);
  const fixture = window.__PRESENTATION_PREVIEW_DEV__ === true ? window.__PRESENTATION_PREVIEW_FIXTURE__ : undefined;
  let connected = false;
  let deck = null;
  let catalog = [];
  let selectedId = null;
  let selectedIssue = null;
  let busy = false;
  let deckEpoch = 0;
  let slideEpoch = 0;
  let previewEpoch = 0;
  let comparisonEpoch = 0;
  let hasInitialResult = false;
  let hasInteracted = false;
  const images = new Map();
  const pendingImages = new Map();

  const shell = document.createElement("div");
  shell.className = "preview-shell";
  const topbar = document.createElement("header");
  topbar.className = "preview-topbar";
  const deckSelect = document.createElement("select");
  deckSelect.className = "deck-select";
  deckSelect.setAttribute("aria-label", "Deck");
  const revision = text("span", "revision", "");
  const refresh = button("Refresh deck", RefreshCw);
  const build = button("Build deck", Hammer);
  const compare = button("Compare styles", GitCompareArrows);
  topbar.append(deckSelect, revision, refresh, build, compare);
  const status = text("div", "status-line", "Waiting for deck");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  const content = document.createElement("div");
  content.className = "preview-content";
  const navigator = document.createElement("nav");
  navigator.className = "slide-navigator";
  navigator.setAttribute("aria-label", "Slides");
  const thumbnailObserver = typeof IntersectionObserver === "function" ? new IntersectionObserver((entries) => {
    if (!hasInteracted || !connected || !app.getHostCapabilities?.()?.serverTools) return;
    for (const entry of entries) {
      if (entry.isIntersecting && entry.target.dataset.slideId) loadPreview(entry.target.dataset.slideId, previewEpoch);
    }
  }, { root: navigator, rootMargin: "80px" }) : null;
  const detail = document.createElement("main");
  detail.className = "slide-detail";
  const heading = text("h1", "slide-title", "Select a deck");
  const slideMeta = text("div", "slide-meta", "");
  const stage = document.createElement("div");
  stage.className = "slide-stage";
  const largeImage = document.createElement("img");
  largeImage.alt = "";
  largeImage.hidden = true;
  const emptyPreview = document.createElement("div");
  emptyPreview.className = "empty-preview";
  emptyPreview.append(icon(ImageOff), text("span", "", "Preview unavailable"));
  stage.append(largeImage, emptyPreview);
  const issuePanel = document.createElement("section");
  issuePanel.className = "issue-panel";
  const issueHeading = text("h2", "panel-heading", "Issues");
  const issueList = document.createElement("ul");
  issuePanel.append(issueHeading, issueList);
  const comparison = document.createElement("section");
  comparison.className = "comparison";
  comparison.hidden = true;
  const comparisonHeading = text("h2", "panel-heading", "Representative cover comparison");
  const comparisonGrid = document.createElement("div");
  comparisonGrid.className = "comparison-grid";
  comparison.append(comparisonHeading, comparisonGrid);
  const revisionForm = document.createElement("form");
  revisionForm.className = "revision-form";
  const request = document.createElement("textarea");
  request.rows = 2;
  request.placeholder = "Describe a slide revision";
  request.setAttribute("aria-label", "Revision request");
  const send = button("Request revision", Send, "send-button");
  send.type = "submit";
  send.append(text("span", "", "Request revision"));
  revisionForm.append(request, send);
  detail.append(heading, slideMeta, stage, issuePanel, comparison, revisionForm);
  content.append(navigator, detail);
  shell.append(topbar, status, content);
  root.append(shell);

  function setStatus(value, kind = "") {
    status.textContent = value;
    status.dataset.kind = kind;
  }

  function setBusy(value) {
    busy = value;
    const capabilities = connected ? app.getHostCapabilities?.() : null;
    const serverTools = Boolean(capabilities?.serverTools);
    const messages = Boolean(openai.message?.send || capabilities?.message?.text);
    refresh.disabled = value || !deck || !serverTools;
    build.disabled = value || !deck || !serverTools;
    compare.disabled = value || !deck || !selectedId || !serverTools;
    send.disabled = value || !deck || !selectedId || !messages;
    deckSelect.disabled = value || !serverTools;
    navigator.querySelectorAll("button").forEach((item) => { item.disabled = value; });
  }

  function applyHost() {
    const context = app.getHostContext?.();
    if (context?.theme) applyDocumentTheme(context.theme);
    if (context?.styles?.variables) applyHostStyleVariables(context.styles.variables);
    root.dataset.theme = context?.theme === "dark" ? "dark" : "light";
    const shared = openai.modelContext?.getCurrent?.()?.structuredContent;
    if (deck && shared?.deck_id === deck.deck_id && shared.revision === deck.revision
      && shared.slide_id !== selectedId && deck.slides.some(slide => slide.slide_id === shared.slide_id)) {
      selectSlide(shared.slide_id);
    }
  }

  function refreshCatalog() {
    const options = catalog.length ? catalog : deck ? [{ deck_id: deck.deck_id, title: deck.title }] : [];
    deckSelect.replaceChildren();
    if (!options.length) {
      const option = new Option("No decks", "");
      deckSelect.add(option);
      return;
    }
    for (const item of options) {
      if (!isObject(item) || typeof item.deck_id !== "string") continue;
      deckSelect.add(new Option(string(item.title, item.deck_id), item.deck_id));
    }
    if (deck && catalog.length < 2) deckSelect.add(new Option("Choose another deck", "__catalog__"));
    if (deck) deckSelect.value = deck.deck_id;
  }

  function currentSlide() {
    return deck?.slides.find((slide) => slide?.slide_id === selectedId) || null;
  }

  function qaLabel() {
    const qa = isObject(deck?.qa) ? deck.qa : {};
    const state = string(qa.state, "Unknown QA");
    const visual = string(qa.visual_review, "not reviewed");
    return `QA: ${state} | Visual review: ${visual}`;
  }

  function syncModelContext() {
    if (!connected || !deck || !selectedId) return;
    const slide = currentSlide();
    if (!slide) return;
    const context = {
      deck_id: deck.deck_id,
      revision: deck.revision,
      slide_id: selectedId,
      slide_index: slide.index,
      title: slide.title,
      variant: slide.variant,
      qa: deck.qa,
      selected_issue: selectedIssue,
    };
    const summary = `Selected slide ${displayIndex(slide.index)}: ${string(slide.title, "Untitled")}. ${qaLabel()}${selectedIssue ? ` Issue: ${selectedIssue}` : ""}`;
    const update = { structuredContent: context, content: [{ type: "text", text: summary }] };
    const method = openai.modelContext?.update
      ? openai.modelContext.update(update)
      : app.getHostCapabilities?.()?.updateModelContext?.text && app.updateModelContext?.(update);
    Promise.resolve(method).catch(() => setStatus("Selection shown; model context unavailable.", "warning"));
  }

  function renderIssues(slide) {
    issueList.replaceChildren();
    const issues = Array.isArray(slide?.issues) ? slide.issues : [];
    issuePanel.hidden = issues.length === 0;
    issueHeading.textContent = issues.some(issue => ["warning", "error"].includes(issue?.severity)) ? "Issues" : "Review notes";
    for (const issue of issues) {
      const item = document.createElement("li");
      const control = document.createElement("button");
      control.type = "button";
      control.className = "issue-button";
      control.textContent = issueLabel(issue);
      control.setAttribute("aria-pressed", String(selectedIssue === issueLabel(issue)));
      control.addEventListener("click", () => {
        selectedIssue = selectedIssue === issueLabel(issue) ? null : issueLabel(issue);
        renderIssues(slide);
        syncModelContext();
      });
      item.append(control);
      issueList.append(item);
    }
  }

  function renderSelection() {
    const slide = currentSlide();
    heading.textContent = string(slide?.title, deck ? "Select a slide" : "Select a deck");
    const count = deck?.slides.length || 0;
    slideMeta.textContent = slide ? `Slide ${displayIndex(slide.index)} of ${count} | ${string(slide.variant, "Default")}` : "";
    revision.textContent = deck ? `Revision ${label(deck.revision, "?").slice(0, 8)}` : "";
    revision.title = deck ? label(deck.revision) : "";
    const key = slide && `${deck.deck_id}:${label(deck.revision)}:${slide.slide_id}`;
    const source = key && images.get(key);
    largeImage.hidden = !source;
    emptyPreview.hidden = Boolean(source);
    if (source) {
      largeImage.src = source;
      largeImage.alt = `Preview of ${string(slide.title, "slide")}`;
    } else largeImage.removeAttribute("src");
    renderIssues(slide);
    [...navigator.querySelectorAll(".slide-item")].forEach((item) => {
      item.setAttribute("aria-current", String(item.dataset.slideId === selectedId));
    });
    setBusy(busy);
  }

  function renderNavigator() {
    thumbnailObserver?.disconnect();
    const scrollLeft = navigator.scrollLeft;
    const scrollTop = navigator.scrollTop;
    navigator.replaceChildren();
    for (const slide of deck?.slides || []) {
      if (!isObject(slide) || typeof slide.slide_id !== "string") continue;
      const item = document.createElement("button");
      item.type = "button";
      item.className = "slide-item";
      item.dataset.slideId = slide.slide_id;
      const thumb = document.createElement("div");
      thumb.className = "slide-thumb";
      const thumbImage = document.createElement("img");
      const key = `${deck.deck_id}:${label(deck.revision)}:${slide.slide_id}`;
      const source = images.get(key);
      if (source) {
        thumbImage.src = source;
        thumbImage.alt = "";
        thumb.append(thumbImage);
      } else thumb.append(text("span", "thumb-number", displayIndex(slide.index)));
      const caption = document.createElement("div");
      caption.className = "thumb-caption";
      caption.append(text("span", "thumb-index", displayIndex(slide.index)), text("span", "thumb-title", string(slide.title, "Untitled")));
      if (Array.isArray(slide.issues) && slide.issues.length) {
        const count = text("span", "issue-count", label(slide.issues.length));
        count.dataset.severity = slide.issues.some(issue => ["warning", "error"].includes(issue?.severity)) ? "warning" : "info";
        caption.append(count);
      }
      item.append(thumb, caption);
      item.addEventListener("click", () => selectSlide(slide.slide_id));
      navigator.append(item);
      if (!source && slide.preview_uri && slide.slide_id !== selectedId) thumbnailObserver?.observe(item);
    }
    navigator.scrollLeft = scrollLeft;
    navigator.scrollTop = scrollTop;
    renderSelection();
  }

  async function tool(name, args) {
    if (!connected || !app.getHostCapabilities?.()?.serverTools) throw new Error("Server tools are unavailable in this host.");
    const result = await app.callServerTool({ name, arguments: args });
    return { data: checkedToolResult(result), result };
  }

  async function loadPreview(slideId, epoch) {
    if (!deck || !selectedId || !slideId || !app.getHostCapabilities?.()?.serverTools) return;
    const key = `${deck.deck_id}:${label(deck.revision)}:${slideId}`;
    if (images.has(key) || pendingImages.get(key) === epoch) return;
    pendingImages.set(key, epoch);
    try {
      const result = await app.callServerTool({
        name: TOOLS.preview,
        arguments: { deck_id: deck.deck_id, revision: deck.revision, slide_id: slideId },
      });
      if (result?.isError) throw new Error("Preview request failed.");
      const source = imageFromResult(result);
      if (!source) throw new Error("No preview image returned.");
      if (epoch !== previewEpoch || !deck || key !== `${deck.deck_id}:${label(deck.revision)}:${slideId}`) return;
      images.set(key, source);
      renderNavigator();
    } catch (error) {
      if (epoch === previewEpoch && slideId === selectedId) setStatus(error.message, "warning");
    } finally {
      if (pendingImages.get(key) === epoch) pendingImages.delete(key);
    }
  }

  async function selectSlide(id) {
    if (!deck || !deck.slides.some((slide) => slide?.slide_id === id)) return;
    hasInteracted = true;
    selectedId = id;
    selectedIssue = null;
    const epoch = ++slideEpoch;
    const currentDeckEpoch = deckEpoch;
    comparison.hidden = true;
    renderNavigator();
    syncModelContext();
    if (!connected || !app.getHostCapabilities?.()?.serverTools) return;
    try {
      const { data, result } = await tool(TOOLS.slide, { deck_id: deck.deck_id, revision: deck.revision, slide_id: id });
      if (epoch !== slideEpoch || currentDeckEpoch !== deckEpoch) return;
      const returnedSlide = data.slide || data;
      if (!slideResult(data) || (data.slide_id && data.slide_id !== id) || (returnedSlide.slide_id && returnedSlide.slide_id !== id)) throw new Error("Slide response did not match the selection.");
      const old = currentSlide();
      Object.assign(old, { title: returnedSlide.title ?? returnedSlide.source?.title ?? old.title, variant: returnedSlide.variant ?? old.variant, issues: returnedSlide.issues ?? old.issues, preview_uri: returnedSlide.preview_uri ?? old.preview_uri });
      const image = imageFromResult(result);
      if (image) images.set(`${deck.deck_id}:${label(deck.revision)}:${id}`, image);
      renderNavigator();
      if (!image && !images.has(`${deck.deck_id}:${label(deck.revision)}:${id}`) && old.preview_uri) loadPreview(id, previewEpoch);
      syncModelContext();
      setStatus(qaLabel(), "qa");
    } catch (error) {
      if (epoch === slideEpoch && currentDeckEpoch === deckEpoch) setStatus(error.message, "error");
    }
  }

  function acceptDeck(data, result = null) {
    if (!deckResult(data)) throw new Error("Deck response is incomplete.");
    ++deckEpoch;
    ++slideEpoch;
    ++previewEpoch;
    ++comparisonEpoch;
    images.clear();
    pendingImages.clear();
    const priorId = deck?.deck_id === data.deck_id ? selectedId : null;
    deck = data;
    if (Array.isArray(data.decks)) catalog = data.decks;
    selectedId = data.slides.some((slide) => slide?.slide_id === priorId) ? priorId : data.slides[0]?.slide_id || null;
    selectedIssue = null;
    const image = imageFromResult(result);
    if (image && selectedId) images.set(`${deck.deck_id}:${label(deck.revision)}:${selectedId}`, image);
    comparison.hidden = true;
    refreshCatalog();
    renderNavigator();
    setStatus(qaLabel(), "qa");
    syncModelContext();
    if (connected && selectedId && !image) loadPreview(selectedId, previewEpoch);
  }

  function acceptCatalog(data) {
    if (!Array.isArray(data?.decks)) throw new Error("Deck catalog is unavailable.");
    catalog = data.decks;
    refreshCatalog();
    setStatus(catalog.length ? "Select a deck" : "No decks available");
  }

  async function openDeck(id) {
    const epoch = ++deckEpoch;
    ++slideEpoch;
    ++previewEpoch;
    setStatus("Opening deck...", "pending");
    setBusy(true);
    try {
      const { data, result } = await tool(TOOLS.open, { deck_id: id });
      if (epoch !== deckEpoch) return;
      if (data.deck_id !== id) throw new Error("Opened deck did not match the request.");
      acceptDeck(data, result);
    } catch (error) {
      if (epoch === deckEpoch) setStatus(error.message, "error");
    } finally {
      if (epoch === deckEpoch || deck?.deck_id === id) setBusy(false);
    }
  }

  function handleHostResult(result) {
    try {
      const data = checkedToolResult(result);
      if (deckResult(data)) {
        hasInitialResult = true;
        acceptDeck(data, result);
      } else if (!hasInitialResult && Array.isArray(data.decks)) {
        hasInitialResult = true;
        acceptCatalog(data);
      }
    } catch (error) {
      if (!hasInitialResult) setStatus(error.message, "error");
    }
  }

  async function buildDeck() {
    if (!deck || busy) return;
    const id = deck.deck_id;
    const previousRevision = deck.revision;
    const epoch = deckEpoch;
    setBusy(true);
    setStatus("Build pending...", "pending");
    try {
      const { data, result } = await tool(TOOLS.build, { deck_id: id, revision: previousRevision });
      if (epoch !== deckEpoch) return;
      if (deckResult(data)) acceptDeck(data, result);
      else if (data.state === "pending" || data.status === "pending") setStatus("Build pending; refresh to check result.", "pending");
      else await openDeck(id);
    } catch (error) {
      if (epoch === deckEpoch) setStatus(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  function comparisonEntries(data) {
    const values = Array.isArray(data?.candidates) ? data.candidates : [];
    if (data?.deck_id && data.deck_id !== deck?.deck_id) return [];
    if (data?.revision && data.revision !== deck?.revision) return [];
    if (data?.slide_id && data.slide_id !== selectedId) return [];
    return values.filter((item) => PRESETS.includes(item?.preset)).slice(0, 3);
  }

  async function audition() {
    if (!deck || !selectedId || busy) return;
    const epoch = ++comparisonEpoch;
    const anchor = `${deck.deck_id}:${label(deck.revision)}:${selectedId}`;
    setBusy(true);
    setStatus("Comparing styles...", "pending");
    try {
      const { data } = await tool(TOOLS.audition, {
        deck_id: deck.deck_id, revision: deck.revision, presets: PRESETS,
      });
      if (epoch !== comparisonEpoch || anchor !== `${deck.deck_id}:${label(deck.revision)}:${selectedId}`) return;
      const entries = comparisonEntries(data);
      const previews = await Promise.all(entries.map(async (entry) => {
        if (!entry.preview_uri) return null;
        try {
          const result = await app.callServerTool({ name: TOOLS.preview, arguments: {
            deck_id: deck.deck_id, revision: deck.revision, slide_id: entry.preview_slide_id, preset: entry.preset,
          } });
          return result?.isError ? null : imageFromResult(result);
        } catch { return null; }
      }));
      if (epoch !== comparisonEpoch || anchor !== `${deck.deck_id}:${label(deck.revision)}:${selectedId}`) return;
      comparisonGrid.replaceChildren();
      entries.forEach((entry, index) => {
        const card = document.createElement("figure");
        const frame = document.createElement("div");
        frame.className = "comparison-frame";
        const source = previews[index];
        if (source) {
          const img = document.createElement("img");
          img.src = source;
          img.alt = `${entry.preset} representative cover preview`;
          frame.append(img);
        } else frame.append(text("span", "", "Preview unavailable"));
        card.append(frame, text("figcaption", "", `${entry.preset} | Cover`));
        const choose = button("Select style", Check, "style-choice");
        choose.append(text("span", "", "Select style"));
        choose.addEventListener("click", () => {
          request.value = `Use ${entry.preset} as the coherent deck style, keeping the content and evidence unchanged.`;
          request.focus();
        });
        card.append(choose);
        comparisonGrid.append(card);
      });
      comparison.hidden = comparisonGrid.childElementCount === 0;
      setStatus(comparison.hidden ? "No comparable previews returned." : "Cover comparisons rendered; visual review pending.", "qa");
    } catch (error) {
      if (epoch === comparisonEpoch) setStatus(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  deckSelect.addEventListener("change", async () => {
    if (deckSelect.value === "__catalog__") {
      try { const { data } = await tool(TOOLS.open, {}); acceptCatalog(data); }
      catch (error) { setStatus(error.message, "error"); }
    } else if (deckSelect.value) openDeck(deckSelect.value);
  });
  refresh.addEventListener("click", () => deck && openDeck(deck.deck_id));
  build.addEventListener("click", buildDeck);
  compare.addEventListener("click", audition);
  revisionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const userRequest = request.value.trim();
    if (!userRequest || !deck || !selectedId || busy || !connected) return;
    const slide = currentSlide();
    const message = `Request revision of deck ${deck.deck_id}, revision ${label(deck.revision)}, slide ${selectedId} (${string(slide?.title, "Untitled")}): ${userRequest}`;
    const payload = { role: "user", content: [{ type: "text", text: message }] };
    setBusy(true);
    try {
      if (openai.message?.send) {
        const result = await openai.message.send(payload);
        if (result?.isError) throw new Error("The host rejected the revision request.");
      }
      else if (app.getHostCapabilities?.()?.message?.text) {
        const result = await app.sendMessage(payload);
        if (result?.isError) throw new Error("The host rejected the revision request.");
      } else throw new Error("This host cannot send revision requests.");
      request.value = "";
      setStatus("Revision request sent. Deck remains unchanged until a new result arrives.", "pending");
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      setBusy(false);
    }
  });

  app.addEventListener("toolresult", handleHostResult);
  app.addEventListener("hostcontextchanged", applyHost);
  applyHost();
  setBusy(false);
  if (fixture !== undefined) {
    // The fixture is opt-in for a standalone browser harness; production state comes only from the host.
    connected = true;
    app.getHostCapabilities = () => ({ serverTools: false });
    handleHostResult(fixture);
    setBusy(false);
  } else {
    app.connect().then(() => {
      connected = true;
      applyHost();
      setBusy(false);
      if (selectedId) syncModelContext();
      else if (!hasInitialResult) setStatus("Waiting for deck result", "pending");
    }).catch((error) => setStatus(`Host connection failed: ${error.message}`, "error"));
  }
}

if (typeof document !== "undefined") setup();
