(function () {
  "use strict";

  const ALLOWED_CASES = [
    "timothy-melanie-weah",
    "michael-carter",
    "daniel-emily-johnson",
    "samantha-lewis"
  ];

  // Initial illustrative names per household (editable by the user; never financial data)
  const CASE_DEFAULTS = {
    "timothy-melanie-weah": {
      label: "Timothy & Melanie Weah",
      members: [
        { name: "Timothy", role: "adult" },
        { name: "Melanie", role: "adult" }
      ],
      contextMembers: ["Timothy", "Melanie", "Liam", "Josh"],
      mainGoals: [
        "Protect the family and review insurance coverage against unexpected events.",
        "Plan ahead and build savings for their children's education.",
        "Prioritize high-interest debt payoff and organize available savings."
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
        "Prepare for retirement and sustain long-term financial plans.",
        "Organize a home purchase while maintaining an emergency cash reserve.",
        "Review financial protection and overall cash flow."
      ],
      defaultPriorities: ["housing", "retirement"]
    },
    "daniel-emily-johnson": {
      label: "Daniel & Emily Johnson",
      members: [
        { name: "Daniel", role: "adult" },
        { name: "Emily", role: "adult" }
      ],
      contextMembers: ["Daniel", "Emily", "Oliver", "Sophia"],
      mainGoals: [
        "Strengthen their retirement plan and household savings.",
        "Protect the family against unexpected events and build a cash reserve.",
        "Plan for their children's education and pay down expensive debt."
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
        "Reinforce her retirement plan and improve monthly cash flow.",
        "Build dedicated savings for her children's education.",
        "Review family protection and upcoming housing plans."
      ],
      defaultPriorities: ["education", "housing"]
    }
  };

  const PRIORITY_OPTIONS = [
    {
      id: "education",
      label: "Children's education",
      help: "Saving for tuition, college, and education—now or in the future."
    },
    {
      id: "retirement",
      label: "Retirement & future",
      help: "Planning savings and income for when you stop working."
    },
    {
      id: "housing",
      label: "Housing",
      help: "Goals related to buying, renting, or maintaining a home."
    },
    {
      id: "security",
      label: "Security & protection",
      help: "Safeguarding your family and income against unexpected events."
    },
    {
      id: "debt",
      label: "Debt reduction",
      help: "Structuring loan repayments and prioritizing high-interest balances."
    },
    {
      id: "investments",
      label: "Savings & investments",
      help: "Saving and investing at a risk level aligned with your goals."
    },
    {
      id: "other",
      label: "Other goals",
      help: "Any other financial topic that matters to your family."
    }
  ];

  const ROLE_OPTIONS = [
    { value: "adult", label: "Adult" },
    { value: "teen", label: "Teenager (entered by parents)" },
    { value: "child", label: "Child (entered by parents)" }
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
    tooltip.setAttribute("aria-label", "Information about " + term + ": " + description);
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
      throw new Error("SherpasQuestionnaire.mount requires a valid HTMLElement container.");
    }
    if (!ALLOWED_CASES.includes(caseId)) {
      throw new Error("Invalid caseId: " + String(caseId));
    }
    if (typeof onSubmit !== "function") {
      throw new Error("SherpasQuestionnaire.mount requires an onSubmit function.");
    }

    // Clear container to prevent duplicates when switching households
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

    // Header
    const header = el("div", "sq-header");
    header.appendChild(el("h3", "sq-title", "Personalize your story — " + preset.label));
    header.appendChild(
      el(
        "p",
        "sq-subtitle",
        "We don't ask for bank details or numbers (they are already in your Sherpas plan). We just want to tailor the story to what matters most to you."
      )
    );
    card.appendChild(header);

    const caseContext = el("div", "sq-case-context");
    caseContext.setAttribute("aria-label", "Context for " + preset.label);
    caseContext.appendChild(el("strong", "sq-context-label", "Household members"));
    caseContext.appendChild(el("p", "sq-context-members", preset.contextMembers.join(", ")));
    caseContext.appendChild(el("strong", "sq-context-label", "Core goals in plan"));
    const goalsList = el("ul", "sq-context-goals");
    preset.mainGoals.forEach((goal) => {
      goalsList.appendChild(el("li", "", goal));
    });
    caseContext.appendChild(goalsList);
    card.appendChild(caseContext);

    const progressSection = el("div", "sq-progress-section");
    const progressLabel = el("span", "sq-progress-label", "Questionnaire progress");
    const progress = el("progress", "sq-progress");
    progress.max = 3;
    progress.value = 0;
    progress.setAttribute("aria-label", "Required sections completed");
    const progressText = el("span", "sq-progress-text", "0 of 3 sections completed");
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
      progressText.textContent = completedSections + " of 3 sections completed";
      progress.setAttribute("aria-valuetext", progressText.textContent);
    }

    updateProgress();

    // 1. Household members section
    const membersSection = el("div", "sq-section");
    membersSection.appendChild(el("h4", "sq-section-title", "1. Who is part of this story?"));
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
            ? "Adult #" + (idx + 1)
            : "Child (optional details entered by parents)";
        top.appendChild(el("strong", "", badgeText));

        if (state.members.length > 1) {
          const removeBtn = el("button", "sq-btn sq-btn-danger", "Remove");
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

        // Name
        const nameField = el("div", "sq-field");
        nameField.appendChild(el("label", "", "First name *"));
        const nameInput = el("input", "sq-input");
        nameInput.type = "text";
        nameInput.maxLength = 100;
        nameInput.placeholder = "e.g., Timothy";
        nameInput.value = member.name;
        nameInput.addEventListener("input", (e) => {
          state.members[idx].name = e.target.value;
          updateProgress();
        });
        nameField.appendChild(nameInput);
        grid.appendChild(nameField);

        // Role
        const roleField = el("div", "sq-field");
        roleField.appendChild(el("label", "", "Household role"));
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

        // Concerns
        const concernsField = el("div", "sq-field");
        concernsField.appendChild(
          el(
            "label",
            "",
            member.role === "adult"
              ? "What worries you most about the future?"
              : "What goal or concern do you have for them? (optional)"
          )
        );
        const concernsInput = el("input", "sq-input");
        concernsInput.type = "text";
        concernsInput.placeholder = "e.g., college tuition, retirement, emergencies";
        concernsInput.value = member.concerns;
        concernsInput.addEventListener("input", (e) => {
          state.members[idx].concerns = e.target.value;
        });
        concernsField.appendChild(concernsInput);
        grid.appendChild(concernsField);

        // Aspirations
        const aspField = el("div", "sq-field");
        aspField.appendChild(
          el(
            "label",
            "",
            member.role === "adult"
              ? "What dream or milestone would you love to achieve?"
              : "What do they dream of studying or achieving? (optional)"
          )
        );
        const aspInput = el("input", "sq-input");
        aspInput.type = "text";
        aspInput.placeholder = "e.g., more free time, peace of mind";
        aspInput.value = member.aspirations;
        aspInput.addEventListener("input", (e) => {
          state.members[idx].aspirations = e.target.value;
        });
        aspField.appendChild(aspInput);
        grid.appendChild(aspField);

        // Non-negotiables
        const nonNegField = el("div", "sq-field");
        nonNegField.appendChild(el("label", "", "What wouldn't you want to sacrifice? (optional)"));
        const nonNegInput = el("input", "sq-input");
        nonNegInput.type = "text";
        nonNegInput.placeholder = "e.g., annual family trips, sports";
        nonNegInput.value = member.non_negotiables;
        nonNegInput.addEventListener("input", (e) => {
          state.members[idx].non_negotiables = e.target.value;
        });
        nonNegField.appendChild(nonNegInput);
        grid.appendChild(nonNegField);

        // Interests / Hobbies
        const intField = el("div", "sq-field");
        intField.appendChild(el("label", "", "Hobbies or free-time interests (optional)"));
        const intInput = el("input", "sq-input");
        intInput.type = "text";
        intInput.placeholder = "e.g., reading, hiking, music";
        intInput.value = member.interests;
        intInput.addEventListener("input", (e) => {
          state.members[idx].interests = e.target.value;
        });
        intField.appendChild(intInput);
        grid.appendChild(intField);

        mCard.appendChild(grid);
        mCard.appendChild(
          el("div", "sq-hint", "You can separate multiple entries with commas (max. 5 per field).")
        );
        membersListEl.appendChild(mCard);
      });
    }

    renderMembers();

    const memberActions = el("div", "sq-btn-row");
    const addAdultBtn = el("button", "sq-btn", "+ Add another adult");
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

    const addChildBtn = el("button", "sq-btn", "+ Add child (optional)");
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

    // 2. Ranked family priorities (1 to 3)
    const prioSection = el("div", "sq-section");
    prioSection.appendChild(
      el("h4", "sq-section-title", "2. Which topics should the video prioritize? (pick 1 to 3 in order)")
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
              showError("You can select a maximum of 3 family priorities.");
              return;
            }
            state.family_priorities.push(opt.id);
          }
          renderPriorities();
          updateProgress();
        });
        if (opt.help) {
          chip.setAttribute("title", opt.help);
          chip.setAttribute("aria-label", opt.label + ". Info: " + opt.help);
          chip.setAttribute("data-tooltip", opt.help);
        }
        chipsContainer.appendChild(chip);
      });

      state.family_priorities.forEach((prioId, index) => {
        const row = el("div", "sq-ordered-item");
        row.appendChild(el("span", "", "#" + (index + 1) + " · " + getPriorityLabel(prioId)));

        const actions = el("div", "sq-order-actions");
        if (index > 0) {
          const upBtn = el("button", "sq-order-btn", "↑");
          upBtn.type = "button";
          upBtn.title = "Move priority up";
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
          downBtn.title = "Move priority down";
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

    // 3. Narration style and main question
    const styleSection = el("div", "sq-section");
    styleSection.appendChild(el("h4", "sq-section-title", "3. How would you like us to explain it?"));
    const styleGrid = el("div", "sq-grid");

    // Financial literacy
    const litField = el("div", "sq-field");
    const litLabel = el("label", "", "Financial detail level");
    appendTooltip(
      litLabel,
      "financial detail level",
      "Controls how many financial terms and technical explanations are included in the narration."
    );
    litField.appendChild(litLabel);
    const litSelect = el("select", "sq-select");
    [
      { value: "beginner", label: "Simple & jargon-free" },
      { value: "intermediate", label: "Balanced, with key details" },
      { value: "advanced", label: "More technical & detailed" }
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

    // Tone
    const toneField = el("div", "sq-field");
    toneField.appendChild(el("label", "", "Narration tone"));
    const toneSelect = el("select", "sq-select");
    [
      { value: "warm", label: "Warm & conversational" },
      { value: "direct", label: "Direct & to the point" }
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

    // Main question
    const qField = el("div", "sq-field");
    qField.style.marginTop = "0.65rem";
    qField.appendChild(el("label", "", "What would you like to understand about your plan today? *"));
    const qInput = el("input", "sq-input");
    qInput.type = "text";
    qInput.maxLength = 500;
    qInput.placeholder = "e.g., Can we afford annual family trips without delaying retirement?";
    qInput.value = state.question;
    qInput.addEventListener("input", (e) => {
      state.question = e.target.value;
      updateProgress();
    });
    qField.appendChild(qInput);

    // Clickable quick-fill questions
    const suggestedQuestions = [
      "Are we on track for a comfortable retirement while maintaining our lifestyle?",
      "How would buying a second home impact our long-term savings?",
      "What happens to our plan if one of us takes 2 years off work?"
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
    card.appendChild(styleSection);

    // Submit button
    const submitBtn = el("button", "sq-btn-primary", "Generate our personalized story");
    submitBtn.type = "button";

    const submitStatus = el("div", "sq-submit-status");
    submitStatus.hidden = true;
    submitStatus.setAttribute("role", "status");
    submitStatus.setAttribute("aria-live", "polite");
    const spinner = el("span", "sq-spinner");
    spinner.setAttribute("aria-hidden", "true");
    submitStatus.appendChild(spinner);
    submitStatus.appendChild(el("span", "", "Submitting questionnaire and preparing your story..."));

    submitBtn.addEventListener("click", async () => {
      showError("");

      // Validations aligned with contracts/questionnaire.schema.json
      if (state.members.length < 1 || state.members.length > 8) {
        showError("There must be between 1 and 8 household participants.");
        return;
      }

      const usedIds = new Set();
      const formattedMembers = [];

      for (let i = 0; i < state.members.length; i += 1) {
        const m = state.members[i];
        const cleanName = String(m.name || "").trim().slice(0, 100);
        if (!cleanName) {
          showError("Please enter a first name for all added participants.");
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
        showError("Please select between 1 and 3 family priorities.");
        return;
      }

      const cleanQuestion = String(state.question || "").trim().slice(0, 500);
      if (!cleanQuestion) {
        showError("Please briefly write what you would like to understand about your plan.");
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
      submitBtn.textContent = "Preparing story...";
      submitStatus.hidden = false;
      try {
        await onSubmit(payload);
      } catch (err) {
        showError("Error submitting questionnaire: " + (err && err.message ? err.message : String(err)));
      } finally {
        submitBtn.disabled = false;
        submitBtn.removeAttribute("aria-busy");
        submitBtn.textContent = "Generate our personalized story";
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