(function () {
  "use strict";

  const ALLOWED_CASES = [
    "timothy-melanie-weah",
    "michael-carter",
    "daniel-emily-johnson",
    "samantha-lewis"
  ];

  // Nombres iniciales orientativos del caso (editables por el usuario; nunca datos financieros)
  const CASE_DEFAULTS = {
    "timothy-melanie-weah": {
      label: "Timothy y Melanie Weah",
      members: [
        { name: "Timothy", role: "adult" },
        { name: "Melanie", role: "adult" }
      ],
      contextMembers: ["Timothy", "Melanie", "Liam", "Josh"],
      mainGoals: [
        "Proteger a la familia y revisar la cobertura ante imprevistos.",
        "Planificar el ahorro para la educación de sus hijos.",
        "Priorizar las deudas con intereses altos y organizar el ahorro disponible."
      ],
      defaultPriorities: ["education", "retirement"]
    },
    "michael-carter": {
      label: "Michael Carter",
      members: [
        { name: "Michael", role: "adult" }
      ],
      contextMembers: ["Michael"],
      mainGoals: [
        "Preparar la jubilación y sostener sus planes a largo plazo.",
        "Organizar la compra de vivienda y mantener una reserva para imprevistos.",
        "Revisar la protección financiera y el flujo de efectivo."
      ],
      defaultPriorities: ["housing", "retirement"]
    },
    "daniel-emily-johnson": {
      label: "Daniel y Emily Johnson",
      members: [
        { name: "Daniel", role: "adult" },
        { name: "Emily", role: "adult" }
      ],
      contextMembers: ["Daniel", "Emily", "Oliver", "Sophia"],
      mainGoals: [
        "Fortalecer el plan de jubilación y el ahorro familiar.",
        "Proteger a la familia ante imprevistos y crear una reserva de efectivo.",
        "Planificar la educación de sus hijos y reducir las deudas más costosas."
      ],
      defaultPriorities: ["debt", "education"]
    },
    "samantha-lewis": {
      label: "Samantha Lewis",
      members: [
        { name: "Samantha", role: "adult" }
      ],
      contextMembers: ["Samantha", "Ethan", "Ava"],
      mainGoals: [
        "Reforzar el plan de jubilación y mejorar el flujo de efectivo.",
        "Preparar el ahorro para la educación de sus hijos.",
        "Revisar la protección de la familia y sus planes de vivienda."
      ],
      defaultPriorities: ["education", "housing"]
    }
  };

  const PRIORITY_OPTIONS = [
    {
      id: "education",
      label: "Educación de los hijos",
      help: "Ahorro para estudios y formación, ahora o en el futuro."
    },
    {
      id: "retirement",
      label: "Jubilación y futuro",
      help: "Planificación del ahorro y los ingresos para cuando dejéis de trabajar."
    },
    {
      id: "housing",
      label: "Vivienda",
      help: "Objetivos relacionados con comprar, alquilar o mantener una vivienda."
    },
    {
      id: "security",
      label: "Seguridad y protección",
      help: "Protección ante imprevistos que puedan afectar a la familia o sus ingresos."
    },
    {
      id: "debt",
      label: "Reducir deudas",
      help: "Organizar el pago de préstamos y priorizar los que tienen intereses más altos."
    },
    {
      id: "investments",
      label: "Ahorro e inversión",
      help: "Ahorrar e invertir con un nivel de riesgo acorde a vuestros objetivos."
    },
    {
      id: "other",
      label: "Otros objetivos",
      help: "Cualquier otro tema financiero que sea importante para la familia."
    }
  ];

  const ROLE_OPTIONS = [
    { value: "adult", label: "Adulto/a" },
    { value: "teen", label: "Adolescente (datos por padres)" },
    { value: "child", label: "Niño/a (datos por padres)" }
  ];

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (typeof text === "string") node.textContent = text;
    return node;
  }

  function appendTooltip(parent, term, description) {
    const tooltip = el("span", "sq-tooltip", "i");
    tooltip.setAttribute("tabindex", "0");
    tooltip.setAttribute("aria-label", "Información sobre " + term + ": " + description);
    tooltip.setAttribute("title", description);
    tooltip.setAttribute("data-tooltip", description);
    parent.appendChild(tooltip);
  }

  function sanitizeMemberId(rawName, index, usedIds) {
    let base = String(rawName || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/g, "_")
      .replace(/^[^a-z0-9]+/, "")
      .replace(/_+/g, "_")
      .slice(0, 50);

    if (!base) {
      base = "member_" + (index + 1);
    }

    let candidate = base;
    let suffix = 2;
    while (usedIds.has(candidate)) {
      candidate = (base + "_" + suffix).slice(0, 64);
      suffix += 1;
    }
    usedIds.add(candidate);
    return candidate;
  }

  function parseShortTextList(rawString) {
    if (!rawString || !rawString.trim()) return [];
    return rawString
      .split(",")
      .map((item) => item.trim().slice(0, 180))
      .filter((item) => item.length > 0)
      .slice(0, 5);
  }

  function mount({ container, caseId, onSubmit }) {
    if (!container || !(container instanceof HTMLElement)) {
      throw new Error("SherpasQuestionnaire.mount requiere un container HTMLElement válido.");
    }
    if (!ALLOWED_CASES.includes(caseId)) {
      throw new Error("caseId no válido: " + String(caseId));
    }
    if (typeof onSubmit !== "function") {
      throw new Error("SherpasQuestionnaire.mount requiere una función onSubmit.");
    }

    // Limpiar contenedor para evitar duplicados al cambiar de familia
    while (container.firstChild) {
      container.removeChild(container.firstChild);
    }

    const preset = CASE_DEFAULTS[caseId];
   const state = {
      members: preset.members.map((m) => ({
        name: m.name,
        role: m.role,
        concerns: "",
        aspirations: "",
        non_negotiables: "",
        interests: ""
      })),
      family_priorities: [],
      literacy: "beginner",
      tone: "warm",
      question: ""
    };

    const card = el("div", "sq-card");

    // Cabecera
    const header = el("div", "sq-header");
    header.appendChild(el("h3", "sq-title", "Personaliza vuestra historia — " + preset.label));
    header.appendChild(
      el(
        "p",
        "sq-subtitle",
        "No pedimos datos bancarios ni cifras (ya están en vuestro plan de Sherpas). Solo queremos adaptar el relato a lo que más os importa."
      )
    );
    card.appendChild(header);

    const caseContext = el("div", "sq-case-context");
    caseContext.setAttribute("aria-label", "Contexto de " + preset.label);
    caseContext.appendChild(el("strong", "sq-context-label", "Miembros de la familia"));
    caseContext.appendChild(el("p", "sq-context-members", preset.contextMembers.join(", ")));
    caseContext.appendChild(el("strong", "sq-context-label", "Objetivos principales"));
    const goalsList = el("ul", "sq-context-goals");
    preset.mainGoals.forEach((goal) => {
      goalsList.appendChild(el("li", "", goal));
    });
    caseContext.appendChild(goalsList);
    card.appendChild(caseContext);

    const progressSection = el("div", "sq-progress-section");
    const progressLabel = el("span", "sq-progress-label", "Progreso del cuestionario");
    const progress = el("progress", "sq-progress");
    progress.max = 3;
    progress.value = 0;
    progress.setAttribute("aria-label", "Secciones obligatorias completadas");
    const progressText = el("span", "sq-progress-text", "0 de 3 secciones completadas");
    progressSection.appendChild(progressLabel);
    progressSection.appendChild(progress);
    progressSection.appendChild(progressText);
    card.appendChild(progressSection);

    const errorBox = el("div", "sq-error");
    errorBox.setAttribute("role", "alert");
    card.appendChild(errorBox);

    function showError(msg) {
      if (!msg) {
        errorBox.style.display = "none";
        errorBox.textContent = "";
      } else {
        errorBox.textContent = msg;
        errorBox.style.display = "block";
      }
    }

    function updateProgress() {
      let completedSections = 0;
      const membersComplete =
        state.members.length >= 1 &&
        state.members.length <= 8 &&
        state.members.every((member) => String(member.name || "").trim().length > 0);

      if (membersComplete) completedSections += 1;
      if (state.family_priorities.length >= 1 && state.family_priorities.length <= 3) {
        completedSections += 1;
      }
      if (String(state.question || "").trim()) completedSections += 1;

      progress.value = completedSections;
      progress.classList.toggle("is-complete", completedSections === 3);
      progressText.textContent = completedSections + " de 3 secciones completadas";
      progress.setAttribute("aria-valuetext", progressText.textContent);
    }

    updateProgress();

    // 1. Sección de miembros
    const membersSection = el("div", "sq-section");
    membersSection.appendChild(el("h4", "sq-section-title", "1. ¿Quién participa en la historia?"));
    const membersListEl = el("div");
    membersSection.appendChild(membersListEl);

    function renderMembers() {
      while (membersListEl.firstChild) {
        membersListEl.removeChild(membersListEl.firstChild);
      }

      state.members.forEach((member, idx) => {
        const mCard = el("div", "sq-member-card");

        const top = el("div", "sq-member-top");
        const badgeText =
          member.role === "adult"
            ? "Adulto/a #" + (idx + 1)
            : "Hijo/a (información opcional de padres)";
        top.appendChild(el("strong", "", badgeText));

        if (state.members.length > 1) {
          const removeBtn = el("button", "sq-btn sq-btn-danger", "Quitar");
          removeBtn.type = "button";
          removeBtn.addEventListener("click", () => {
            state.members.splice(idx, 1);
            renderMembers();
            updateProgress();
          });
          top.appendChild(removeBtn);
        }
        mCard.appendChild(top);

        const grid = el("div", "sq-grid");

        // Nombre
        const nameField = el("div", "sq-field");
        nameField.appendChild(el("label", "", "¿Cómo quieres que te llamemos? *"));
        const nameInput = el("input", "sq-input");
        nameInput.type = "text";
        nameInput.maxLength = 100;
        nameInput.placeholder = "Ej: Timothy";
        nameInput.value = member.name;
        nameInput.addEventListener("input", (e) => {
          state.members[idx].name = e.target.value;
          updateProgress();
        });
        nameField.appendChild(nameInput);
        grid.appendChild(nameField);

        // Rol
        const roleField = el("div", "sq-field");
        roleField.appendChild(el("label", "", "Perfil en la familia"));
        const roleSelect = el("select", "sq-select");
        ROLE_OPTIONS.forEach((opt) => {
          const o = el("option", "", opt.label);
          o.value = opt.value;
          if (opt.value === member.role) o.selected = true;
          roleSelect.appendChild(o);
        });
        roleSelect.addEventListener("change", (e) => {
          state.members[idx].role = e.target.value;
          renderMembers();
          updateProgress();
        });
        roleField.appendChild(roleSelect);
        grid.appendChild(roleField);

        // Preocupaciones
        const concernsField = el("div", "sq-field");
        concernsField.appendChild(
          el(
            "label",
            "",
            member.role === "adult"
              ? "¿Qué te preocupa más del futuro?"
              : "¿Qué objetivo os preocupa para él/ella? (opcional)"
          )
        );
        const concernsInput = el("input", "sq-input");
        concernsInput.type = "text";
        concernsInput.placeholder = "Ej: universidad, jubilación, imprevistos";
        concernsInput.value = member.concerns;
        concernsInput.addEventListener("input", (e) => {
          state.members[idx].concerns = e.target.value;
        });
        concernsField.appendChild(concernsInput);
        grid.appendChild(concernsField);

        // Aspiraciones
        const aspField = el("div", "sq-field");
        aspField.appendChild(
          el(
            "label",
            "",
            member.role === "adult"
              ? "¿Qué ilusión o meta te gustaría alcanzar?"
              : "¿Qué sueña estudiar o lograr? (opcional)"
          )
        );
        const aspInput = el("input", "sq-input");
        aspInput.type = "text";
        aspInput.placeholder = "Ej: más tiempo libre, tranquilidad";
        aspInput.value = member.aspirations;
        aspInput.addEventListener("input", (e) => {
          state.members[idx].aspirations = e.target.value;
        });
        aspField.appendChild(aspInput);
        grid.appendChild(aspField);

        // No negociables
        const nonNegField = el("div", "sq-field");
        nonNegField.appendChild(el("label", "", "¿Qué no querrías sacrificar? (opcional)"));
        const nonNegInput = el("input", "sq-input");
        nonNegInput.type = "text";
        nonNegInput.placeholder = "Ej: vacaciones en familia, deporte";
        nonNegInput.value = member.non_negotiables;
        nonNegInput.addEventListener("input", (e) => {
          state.members[idx].non_negotiables = e.target.value;
        });
        nonNegField.appendChild(nonNegInput);
        grid.appendChild(nonNegField);

        // Intereses / Hobbies
        const intField = el("div", "sq-field");
        intField.appendChild(el("label", "", "Aficiones o tiempo libre (opcional)"));
        const intInput = el("input", "sq-input");
        intInput.type = "text";
        intInput.placeholder = "Ej: lectura, senderismo, música";
        intInput.value = member.interests;
        intInput.addEventListener("input", (e) => {
          state.members[idx].interests = e.target.value;
        });
        intField.appendChild(intInput);
        grid.appendChild(intField);

        mCard.appendChild(grid);
        mCard.appendChild(
          el("div", "sq-hint", "Puedes separar varias respuestas con comas (máx. 5 por campo).")
        );
        membersListEl.appendChild(mCard);
      });
    }

    renderMembers();

    const memberActions = el("div", "sq-btn-row");
    const addAdultBtn = el("button", "sq-btn", "+ Añadir otro adulto");
    addAdultBtn.type = "button";
    addAdultBtn.addEventListener("click", () => {
      if (state.members.length >= 8) return;
      state.members.push({
        name: "",
        role: "adult",
        concerns: "",
        aspirations: "",
        non_negotiables: "",
        interests: ""
      });
      renderMembers();
      updateProgress();
    });

    const addChildBtn = el("button", "sq-btn", "+ Añadir hijo/a (opcional)");
    addChildBtn.type = "button";
    addChildBtn.addEventListener("click", () => {
      if (state.members.length >= 8) return;
      state.members.push({
        name: "",
        role: "child",
        concerns: "",
        aspirations: "",
        non_negotiables: "",
        interests: ""
      });
      renderMembers();
      updateProgress();
    });

    memberActions.appendChild(addAdultBtn);
    memberActions.appendChild(addChildBtn);
    membersSection.appendChild(memberActions);
    card.appendChild(membersSection);

    // 2. Prioridades familiares ordenadas (1 a 3)
    const prioSection = el("div", "sq-section");
    prioSection.appendChild(
      el("h4", "sq-section-title", "2. ¿Qué temas queréis priorizar en el vídeo? (elige 1 a 3 en orden)")
    );
    const prioWrap = el("div", "sq-priorities-wrap");
    const chipsContainer = el("div", "sq-priority-chips");
    const orderedContainer = el("div", "sq-ordered-list");

    function getPriorityLabel(id) {
      const found = PRIORITY_OPTIONS.find((p) => p.id === id);
      return found ? found.label : id;
    }

    function renderPriorities() {
      while (chipsContainer.firstChild) chipsContainer.removeChild(chipsContainer.firstChild);
      while (orderedContainer.firstChild) orderedContainer.removeChild(orderedContainer.firstChild);

      PRIORITY_OPTIONS.forEach((opt) => {
        const isSelected = state.family_priorities.includes(opt.id);
        const chip = el("button", "sq-chip" + (isSelected ? " selected" : ""), opt.label);
        chip.type = "button";
        chip.addEventListener("click", () => {
          showError("");
          const pos = state.family_priorities.indexOf(opt.id);
          if (pos !== -1) {
            state.family_priorities.splice(pos, 1);
          } else {
            if (state.family_priorities.length >= 3) {
              showError("Puedes seleccionar un máximo de 3 prioridades familiares.");
              return;
            }
            state.family_priorities.push(opt.id);
          }
          renderPriorities();
          updateProgress();
        });
        if (opt.help) {
          chip.setAttribute("title", opt.help);
          chip.setAttribute("aria-label", opt.label + ". Información: " + opt.help);
          chip.setAttribute("data-tooltip", opt.help);
        }
        chipsContainer.appendChild(chip);
      });

      state.family_priorities.forEach((prioId, index) => {
        const row = el("div", "sq-ordered-item");
        row.appendChild(el("span", "", (index + 1) + "º · " + getPriorityLabel(prioId)));

        const actions = el("div", "sq-order-actions");
        if (index > 0) {
          const upBtn = el("button", "sq-order-btn", "↑");
          upBtn.type = "button";
          upBtn.title = "Subir prioridad";
          upBtn.addEventListener("click", () => {
            const tmp = state.family_priorities[index - 1];
            state.family_priorities[index - 1] = state.family_priorities[index];
            state.family_priorities[index] = tmp;
            renderPriorities();
          });
          actions.appendChild(upBtn);
        }
        if (index < state.family_priorities.length - 1) {
          const downBtn = el("button", "sq-order-btn", "↓");
          downBtn.type = "button";
          downBtn.title = "Bajar prioridad";
          downBtn.addEventListener("click", () => {
            const tmp = state.family_priorities[index + 1];
            state.family_priorities[index + 1] = state.family_priorities[index];
            state.family_priorities[index] = tmp;
            renderPriorities();
          });
          actions.appendChild(downBtn);
        }
        row.appendChild(actions);
        orderedContainer.appendChild(row);
      });
    }

    renderPriorities();
    prioWrap.appendChild(chipsContainer);
    prioWrap.appendChild(orderedContainer);
    prioSection.appendChild(prioWrap);
    card.appendChild(prioSection);

    // 3. Estilo de explicación y pregunta inicial
    const styleSection = el("div", "sq-section");
    styleSection.appendChild(el("h4", "sq-section-title", "3. ¿Cómo preferís que os lo contemos?"));
    const styleGrid = el("div", "sq-grid");

    // Nivel financiero
    const litField = el("div", "sq-field");
    const litLabel = el("label", "", "Nivel de detalle financiero");
    appendTooltip(
      litLabel,
      "nivel de detalle financiero",
      "Indica cuántos términos y explicaciones financieras queréis incluir en la narración."
    );
    litField.appendChild(litLabel);
    const litSelect = el("select", "sq-select");
    [
      { value: "beginner", label: "Sencillo y sin tecnicismos" },
      { value: "intermediate", label: "Equilibrado, con algún detalle" },
      { value: "advanced", label: "Más técnico y detallado" }
    ].forEach((opt) => {
      const o = el("option", "", opt.label);
      o.value = opt.value;
      if (opt.value === state.literacy) o.selected = true;
      litSelect.appendChild(o);
    });
    litSelect.addEventListener("change", (e) => {
      state.literacy = e.target.value;
    });
    litField.appendChild(litSelect);
    styleGrid.appendChild(litField);

    // Tono
    const toneField = el("div", "sq-field");
    toneField.appendChild(el("label", "", "Tono de la narración"));
    const toneSelect = el("select", "sq-select");
    [
      { value: "warm", label: "Cercano y familiar" },
      { value: "direct", label: "Directo y al grano" }
    ].forEach((opt) => {
      const o = el("option", "", opt.label);
      o.value = opt.value;
      if (opt.value === state.tone) o.selected = true;
      toneSelect.appendChild(o);
    });
    toneSelect.addEventListener("change", (e) => {
      state.tone = e.target.value;
    });
    toneField.appendChild(toneSelect);
    styleGrid.appendChild(toneField);

    styleSection.appendChild(styleGrid);

    // Pregunta / motivo general
  // Pregunta / motivo general
    const qField = el("div", "sq-field");
    qField.style.marginTop = "0.65rem";
    qField.appendChild(el("label", "", "¿Qué os gustaría entender hoy de vuestro plan? *"));
    const qInput = el("input", "sq-input");
    qInput.type = "text";
    qInput.maxLength = 500;
    qInput.placeholder = "Ej: ¿Podemos permitirnos viajar cada año sin retrasar la jubilación?";
    qInput.value = state.question;
    qInput.addEventListener("input", (e) => {
      state.question = e.target.value;
      updateProgress();
    });
    qField.appendChild(qInput);

    // Preguntas rápidas clicables
    const suggestedQuestions = [
      "¿Llegamos cómodos a la jubilación manteniendo nuestro nivel de vida?",
      "¿Cómo afecta comprar una segunda vivienda a nuestros ahorros?",
      "¿Qué pasa con el plan si uno de los dos deja de trabajar 2 años?"
    ];
    const suggestionsBox = el("div", "sq-question-suggestions");
    suggestedQuestions.forEach((text) => {
      const chip = el("button", "sq-suggestion-chip", text);
      chip.type = "button";
      chip.addEventListener("click", () => {
        qInput.value = text;
        state.question = text;
        updateProgress();
      });
      suggestionsBox.appendChild(chip);
    });
    qField.appendChild(suggestionsBox);

    styleSection.appendChild(qField);
    styleSection.appendChild(qField);

    card.appendChild(styleSection);
    // Botón enviar
    const submitBtn = el("button", "sq-btn-primary", "Generar nuestra historia personalizada");
    submitBtn.type = "button";

    const submitStatus = el("div", "sq-submit-status");
    submitStatus.hidden = true;
    submitStatus.setAttribute("role", "status");
    submitStatus.setAttribute("aria-live", "polite");
    const spinner = el("span", "sq-spinner");
    spinner.setAttribute("aria-hidden", "true");
    submitStatus.appendChild(spinner);
    submitStatus.appendChild(el("span", "", "Enviando el cuestionario y preparando vuestra historia..."));

    submitBtn.addEventListener("click", async () => {
      showError("");

      // Validaciones acordes a contracts/questionnaire.schema.json
      if (state.members.length < 1 || state.members.length > 8) {
        showError("Debe haber entre 1 y 8 participantes.");
        return;
      }

      const usedIds = new Set();
      const formattedMembers = [];

      for (let i = 0; i < state.members.length; i += 1) {
        const m = state.members[i];
        const cleanName = String(m.name || "").trim().slice(0, 100);
        if (!cleanName) {
          showError("Por favor, indica un nombre para todos los participantes añadidos.");
          return;
        }
        formattedMembers.push({
          member_id: sanitizeMemberId(cleanName, i, usedIds),
          name: cleanName,
          role: m.role,
          interests: parseShortTextList(m.interests),
          aspirations: parseShortTextList(m.aspirations),
          concerns: parseShortTextList(m.concerns),
          non_negotiables: parseShortTextList(m.non_negotiables)
        });
      }

      if (state.family_priorities.length < 1 || state.family_priorities.length > 3) {
        showError("Selecciona entre 1 y 3 prioridades familiares.");
        return;
      }

      const cleanQuestion = String(state.question || "").trim().slice(0, 500);
      if (!cleanQuestion) {
        showError("Escribe brevemente qué os gustaría entender de vuestro plan.");
        return;
      }

      const payload = {
        schema_version: "1.0",
        case_id: caseId,
        profile: {
          members: formattedMembers,
          family_priorities: [...state.family_priorities],
          literacy: state.literacy,
          tone: state.tone
        },
        question: cleanQuestion
      };

      submitBtn.disabled = true;
      submitBtn.setAttribute("aria-busy", "true");
      submitBtn.textContent = "Preparando historia...";
      submitStatus.hidden = false;
      try {
        await onSubmit(payload);
      } catch (err) {
        showError("Error al enviar el cuestionario: " + (err && err.message ? err.message : String(err)));
      } finally {
        submitBtn.disabled = false;
        submitBtn.removeAttribute("aria-busy");
        submitBtn.textContent = "Generar nuestra historia personalizada";
        submitStatus.hidden = true;
      }
    });

    card.appendChild(submitStatus);
    card.appendChild(submitBtn);
    container.appendChild(card);
  }

  window.SherpasQuestionnaire = {
    mount: mount
  };
})();