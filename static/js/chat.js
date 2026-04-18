/**
 * Cortex Analyst chat UI: question chips, text input, and transcript rendering.
 *
 * Tracks an AbortController so re-initialization (on re-reveal) removes
 * old form listeners, preventing duplicate submissions.
 */

import { fetchAsk } from "./api.js";

const DEFAULT_CHIPS = [
  "How much has this mine produced since 2020?",
  "What other plants buy from this operator?",
  "Is this mine still active?",
  "What is the total coal tonnage for this subregion in 2024?",
  "Who is the largest coal supplier in this state?",
];

let chatAbortController = null;
let chatBusy = false;

/**
 * Initialize the chat UI with chips and event handlers.
 * Safe to call multiple times — previous listeners are removed.
 * @param {Object} params
 * @param {HTMLElement} params.chipsContainer
 * @param {HTMLFormElement} params.form
 * @param {HTMLInputElement} params.input
 * @param {HTMLElement} params.transcript
 * @param {string} params.subregionId
 * @param {string} params.mineName
 * @param {string} params.mineOperator
 * @param {string} params.mineState
 */
export function initChat(params) {
  const {
    chipsContainer,
    form,
    input,
    transcript,
    subregionId,
    mineName,
    mineOperator,
    mineState,
  } = params;

  // Abort previous listeners to prevent stacking on re-reveal
  if (chatAbortController) {
    chatAbortController.abort();
  }
  chatAbortController = new AbortController();
  const signal = chatAbortController.signal;

  chatBusy = false;

  const chipQuestions = DEFAULT_CHIPS.map((q) =>
    q
      .replace("this mine", mineName)
      .replace("this operator", mineOperator)
      .replace("this subregion", subregionId)
      .replace("this state", mineState),
  );

  renderChips(chipsContainer, chipQuestions, (question) => {
    submitQuestion(question, subregionId, transcript, form, input);
  }, signal);

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    input.value = "";
    submitQuestion(question, subregionId, transcript, form, input);
  }, { signal });
}

/**
 * Render chip buttons into the container.
 * @param {HTMLElement} container
 * @param {string[]} questions
 * @param {function} onClick
 * @param {AbortSignal} signal
 */
function renderChips(container, questions, onClick, signal) {
  container.replaceChildren();
  for (const q of questions) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chat__chip";
    chip.textContent = q;
    chip.addEventListener("click", () => onClick(q), { signal });
    container.appendChild(chip);
  }
}

/**
 * Submit a question to the /ask endpoint and render the result.
 * Prevents concurrent submissions by disabling the form while busy.
 * @param {string} question
 * @param {string} subregionId
 * @param {HTMLElement} transcript
 * @param {HTMLFormElement} form
 * @param {HTMLInputElement} input
 */
async function submitQuestion(question, subregionId, transcript, form, input) {
  if (chatBusy) return;
  chatBusy = true;
  setFormEnabled(form, input, false);

  const exchange = createExchangeEl(question);
  transcript.prepend(exchange);

  try {
    const data = await fetchAsk(question, subregionId);
    renderAnswer(exchange, data, subregionId, transcript, form, input);
  } catch (err) {
    renderError(exchange, err.message || "Something went wrong. Please try again.");
  } finally {
    chatBusy = false;
    setFormEnabled(form, input, true);
  }
}

/**
 * Enable or disable the chat form controls.
 * @param {HTMLFormElement} form
 * @param {HTMLInputElement} input
 * @param {boolean} enabled
 */
function setFormEnabled(form, input, enabled) {
  const submitBtn = form.querySelector("button[type='submit']");
  if (submitBtn) submitBtn.disabled = !enabled;
  input.disabled = !enabled;
}

/**
 * Create a chat exchange element with the question and a loading indicator.
 * @param {string} question
 * @returns {HTMLElement}
 */
function createExchangeEl(question) {
  const el = document.createElement("div");
  el.className = "chat__exchange";

  const questionEl = document.createElement("div");
  questionEl.className = "chat__question";
  questionEl.textContent = question;
  el.appendChild(questionEl);

  const loadingEl = document.createElement("div");
  loadingEl.className = "chat__loading";
  loadingEl.textContent = "Thinking...";
  el.appendChild(loadingEl);

  return el;
}

/**
 * Render the answer, SQL, and results into an exchange element.
 * @param {HTMLElement} exchange
 * @param {Object} data - AskResponse
 * @param {string} subregionId
 * @param {HTMLElement} transcript
 * @param {HTMLFormElement} form
 * @param {HTMLInputElement} input
 */
function renderAnswer(exchange, data, subregionId, transcript, form, input) {
  const loading = exchange.querySelector(".chat__loading");
  if (loading) loading.remove();

  if (data.error) {
    const errorEl = document.createElement("div");
    errorEl.className = "chat__error";
    errorEl.textContent = data.error;
    exchange.appendChild(errorEl);
  }

  if (data.answer) {
    const answerEl = document.createElement("div");
    answerEl.className = "chat__answer";
    answerEl.textContent = data.answer;
    exchange.appendChild(answerEl);
  }

  if (data.sql) {
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "chat__sql-toggle";
    toggle.textContent = "Show SQL";
    exchange.appendChild(toggle);

    const sqlEl = document.createElement("pre");
    sqlEl.className = "chat__sql hidden";
    sqlEl.textContent = data.sql;
    exchange.appendChild(sqlEl);

    toggle.addEventListener("click", () => {
      const isHidden = sqlEl.classList.toggle("hidden");
      toggle.textContent = isHidden ? "Show SQL" : "Hide SQL";
    });
  }

  if (data.results && data.results.length > 0) {
    exchange.appendChild(renderResultsTable(data.results));
  }

  if (data.suggestions && data.suggestions.length > 0) {
    const suggestionsEl = document.createElement("div");
    suggestionsEl.className = "chat__chips";
    suggestionsEl.style.marginTop = "0.75rem";

    for (const s of data.suggestions) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chat__chip";
      chip.textContent = s;
      chip.addEventListener("click", () => {
        submitQuestion(s, subregionId, transcript, form, input);
      });
      suggestionsEl.appendChild(chip);
    }

    exchange.appendChild(suggestionsEl);
  }
}

/**
 * Render an error message into an exchange element.
 * @param {HTMLElement} exchange
 * @param {string} message
 */
function renderError(exchange, message) {
  const loading = exchange.querySelector(".chat__loading");
  if (loading) loading.remove();

  const errorEl = document.createElement("div");
  errorEl.className = "chat__error";
  errorEl.textContent = message;
  exchange.appendChild(errorEl);
}

/**
 * Build an HTML table from an array of row objects.
 * @param {Object[]} rows
 * @returns {HTMLElement}
 */
function renderResultsTable(rows) {
  const wrapper = document.createElement("div");
  wrapper.className = "chat__results";

  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  const keys = Object.keys(rows[0]);

  for (const key of keys) {
    const th = document.createElement("th");
    th.textContent = key;
    headerRow.appendChild(th);
  }
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const key of keys) {
      const td = document.createElement("td");
      const val = row[key];
      td.textContent = val !== null && val !== undefined ? String(val) : "";
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  wrapper.appendChild(table);

  return wrapper;
}
