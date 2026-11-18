/* SHERPAS · Interactive Audiovisual Player · Annual Escalation Edition
- Public API: window.SherpasVideo.mount({ container, story, onAsk, onSceneChange })
- Visualizes year-by-year financial escalation as decisions are applied and unlocks the tracker on ending.
 */
(function () {
  'use strict';

  const safeText = (value) => String(value ?? '');
  const make = (tag, className, text) => {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = safeText(text);
    return el;
  };
  const THEMES = new Set(['family_travel', 'dream_home', 'early_retirement', 'financial_shield']);

  function validateStory(story) {
    if (!story || !Array.isArray(story.scenes) || story.scenes.length < 3) {
      throw new Error('A valid story with at least 3 scenes is required.');
    }
    const sceneMap = new Map();
    for (const scene of story.scenes) {
      if (!scene.id || sceneMap.has(scene.id)) throw new Error('Scenes have missing or duplicate IDs.');
      if (!THEMES.has(scene.visual_theme) || !scene.headline || !scene.narration || !scene.metric_badge) {
        throw new Error('Each scene must include theme, headline, narration, and metric badge.');
      }
      sceneMap.set(scene.id, scene);
    }
    if (!sceneMap.has(story.start_scene_id)) throw new Error('Start scene does not exist.');
    for (const scene of story.scenes) {
      if (scene.next_scene_id && !sceneMap.has(scene.next_scene_id)) throw new Error(`Missing next scene: ${scene.next_scene_id}`);
      for (const choice of (scene.choices || [])) {
        if (!sceneMap.has(choice.next_scene_id)) throw new Error(`Missing choice route: ${choice.next_scene_id}`);
      }
    }
    return sceneMap;
  }

  function mount({ container, story, onAsk, onSceneChange } = {}) {
    if (!(container instanceof HTMLElement)) throw new Error('container must be a valid HTML element.');
    const sceneMap = validateStory(story);
    const askHandler = typeof onAsk === 'function' ? onAsk : null;
    const sceneChangeHandler = typeof onSceneChange === 'function' ? onSceneChange : null;
    const ladder = Array.isArray(story.escalation_ladder) ? story.escalation_ladder : [];

    let currentId = story.start_scene_id;
    let history = [];
    let audio = null;
    let utterance = null;
    let paused = false;
    let playbackId = 0;
    let destroyed = false;
    let waitingAnswer = false;
    let answerAudio = null;

    container.replaceChildren();
    const root = make('section', 'sv-root');
    root.setAttribute('aria-label', 'Interactive financial story');
    const device = make('div', 'sv-device');
    const top = make('header', 'sv-header');
    const eyebrow = make('div', 'sv-eyebrow', 'SHERPAS · ANNUAL ESCALATION PLAN');
    const storyTitle = make('h2', 'sv-story-title', story.title);
    const disclaimer = make('p', 'sv-disclaimer', story.disclaimer);
    const step = make('div', 'sv-step', '');
    const progressTrack = make('div', 'sv-progress-track');
    progressTrack.setAttribute('role', 'progressbar');
    progressTrack.setAttribute('aria-label', 'Story progress');
    progressTrack.setAttribute('aria-valuemin', '1');
    progressTrack.setAttribute('aria-valuemax', String(story.scenes.length));
    const progressFill = make('div', 'sv-progress-fill');
    progressTrack.append(progressFill);

    // Visual Year-by-Year Escalation Strip
    const ladderStrip = make('div', 'sv-ladder');
    ladderStrip.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin-top:12px;';
    const ladderCards = ladder.map((item) => {
      const card = make('div', 'sv-ladder-step');
      card.style.cssText = 'padding:8px 10px;border-radius:10px;border:1px solid #cbd5e1;background:#f8fafc;text-align:left;transition:all 0.25s ease;';
      const yrEl = make('div', '', `📅 ${item.year}`);
      yrEl.style.cssText = 'font-size:0.75rem;font-weight:800;color:#475569;';
      const nwEl = make('div', '', item.net_worth_formatted || `Score ${item.projected_score}`);
      nwEl.style.cssText = 'font-size:0.88rem;font-weight:800;color:#0f172a;margin-top:2px;';
      const scEl = make('div', '', `Health: ${item.projected_score}/100`);
      scEl.style.cssText = 'font-size:0.72rem;font-weight:600;color:#2563eb;margin-top:1px;';
      card.append(yrEl, nwEl, scEl);
      ladderStrip.append(card);
      return { stepIndex: item.step_index, el: card, yrEl, nwEl, scEl };
    });

    const stage = make('main', 'sv-stage');
    const year = make('div', 'sv-year');
    const symbol = make('div', 'sv-symbol');
    const headline = make('h3', 'sv-scene-title');
    const metric = make('div', 'sv-metric');
    const metricLabel = make('div', 'sv-metric-label');
    const metricValue = make('div', 'sv-metric-value');
    metric.append(metricLabel, metricValue);
    const narration = make('p', 'sv-narration');
    const source = make('div', 'sv-source');
    const choices = make('div', 'sv-choices');
    const answerBox = make('div', 'sv-answer');
    answerBox.hidden = true;
    const answerText = make('p', 'sv-answer-text');
    const continueAfterAsk = make('button', 'sv-btn sv-answer-next', '↻ Replay this year');
    answerBox.append(answerText, continueAfterAsk);
    stage.append(year, symbol, headline, metric, narration, source, choices, answerBox);

    const controls = make('div', 'sv-controls');
    const back = make('button', 'sv-btn sv-muted', '← Back');
    const pause = make('button', 'sv-btn sv-muted', '⏸ Pause');
    const next = make('button', 'sv-btn sv-primary', 'Next →');
    controls.append(back, pause, next);

    const questions = make('form', 'sv-qa');
    const questionLabel = make('label', 'sv-qa-label', 'Questions about this year or decision?');
    const questionInput = make('input', 'sv-qa-input');
    questionInput.type = 'text';
    questionInput.placeholder = 'e.g., How does this decision boost our net worth by this year?';
    questionInput.maxLength = 500;
    questionInput.autocomplete = 'off';
    questionLabel.htmlFor = 'sv-question-' + Math.random().toString(36).slice(2, 8);
    questionInput.id = questionLabel.htmlFor;
    const ask = make('button', 'sv-btn sv-ask', 'Ask');
    ask.type = 'submit';
    questions.append(questionLabel, questionInput, ask);

    top.append(eyebrow, storyTitle, disclaimer, step, progressTrack);
    if (ladderCards.length > 0) top.append(ladderStrip);
    device.append(top, stage, controls, questions);
    root.append(device);
    container.append(root);

    const visuals = {
      family_travel: '✈️',
      dream_home: '🏡',
      early_retirement: '🌅',
      financial_shield: '🛡️'
    };

    function updateLadderHighlight(activeStep) {
      for (const item of ladderCards) {
        if (activeStep > 0 && item.stepIndex === activeStep) {
          item.el.style.background = '#eff6ff';
          item.el.style.borderColor = '#2563eb';
          item.el.style.boxShadow = '0 2px 8px rgba(37, 99, 235, 0.18)';
          item.yrEl.style.color = '#1d4ed8';
        } else if (activeStep > 0 && item.stepIndex < activeStep) {
          item.el.style.background = '#f0fdf4';
          item.el.style.borderColor = '#86efac';
          item.el.style.boxShadow = 'none';
          item.yrEl.style.color = '#15803d';
        } else {
          item.el.style.background = '#f8fafc';
          item.el.style.borderColor = '#cbd5e1';
          item.el.style.boxShadow = 'none';
          item.yrEl.style.color = '#475569';
        }
      }
    }

    function stopSpeech() {
      playbackId += 1;
      if (audio) {
        audio.onended = null;
        audio.pause();
        audio = null;
      }
      if ('speechSynthesis' in window) window.speechSynthesis.cancel();
      utterance = null;
    }
    function stopAnswerAudio() {
      if (answerAudio) {
        answerAudio.pause();
        answerAudio = null;
      }
    }
    function speak(scene) {
      stopSpeech();
      paused = false;
      pause.textContent = '⏸ Pause';
      const thisPlayback = playbackId;
      const finished = () => {
        if (destroyed || paused || thisPlayback !== playbackId || waitingAnswer) return;
        if (scene.kind === 'narration' && scene.next_scene_id) goTo(scene.next_scene_id, true);
      };
      if (scene.audio_b64) {
        audio = new Audio('data:audio/mpeg;base64,' + scene.audio_b64);
        audio.onended = finished;
        audio.play().catch(() => { /* Manual playback controls available */ });
      } else if ('speechSynthesis' in window && scene.narration) {
        utterance = new SpeechSynthesisUtterance(scene.narration);
        utterance.lang = 'en-US';
        utterance.rate = 0.97;
        utterance.onend = finished;
        window.speechSynthesis.speak(utterance);
      }
    }
    function render() {
      const scene = sceneMap.get(currentId);
      const sceneIndex = story.scenes.findIndex((item) => item.id === currentId);
      const currentStep = sceneIndex + 1;
      progressFill.style.width = `${(currentStep / story.scenes.length) * 100}%`;
      progressTrack.setAttribute('aria-valuenow', String(currentStep));
      progressTrack.setAttribute('aria-valuetext', `Stage ${currentStep} of ${story.scenes.length}`);
      step.textContent = `STAGE ${currentStep} OF ${story.scenes.length}`;
      updateLadderHighlight(Number(scene.escalation_step || 0));

      answerBox.hidden = true;
      waitingAnswer = false;
      questionInput.value = '';
      year.textContent = scene.year === null ? safeText(scene.period_label) : String(scene.year);
      symbol.textContent = visuals[scene.visual_theme];
      headline.textContent = safeText(scene.headline);
      stage.dataset.theme = scene.visual_theme;
      narration.textContent = safeText(scene.narration);
      metric.hidden = !scene.metric_badge;
      if (scene.metric_badge) {
        metricLabel.textContent = safeText(scene.metric_badge.label);
        metricValue.textContent = safeText(scene.metric_badge.value);
      }
      source.textContent = scene.metric_badge && scene.metric_badge.source_ref
        ? 'Source: ' + safeText(scene.metric_badge.source_ref)
        : '';
      source.hidden = !source.textContent;
      stage.classList.remove('sv-scene-enter');
      void stage.offsetWidth;
      stage.classList.add('sv-scene-enter');
      choices.replaceChildren();
      if (scene.kind === 'choice') {
        for (const choice of (scene.choices || [])) {
          const button = make('button', 'sv-choice', choice.label);
          button.type = 'button';
          button.addEventListener('click', () => goTo(choice.next_scene_id, true));
          choices.append(button);
        }
      }
      back.disabled = history.length === 0;
      next.disabled = scene.kind === 'choice';
      next.textContent = scene.kind === 'ending' ? '↻ Restart story' : 'Next →';
      pause.disabled = !scene.narration;
      questions.hidden = !askHandler;
      if (story.data_status === 'mock') root.classList.add('sv-is-mock');
      else root.classList.remove('sv-is-mock');
      speak(scene);
      if (sceneChangeHandler) sceneChangeHandler(scene);
    }
    function goTo(id, remember) {
      if (destroyed || !sceneMap.has(id)) return;
      stopAnswerAudio();
      if (remember) history.push(currentId);
      currentId = id;
      render();
    }
    back.addEventListener('click', () => {
      if (!history.length) return;
      currentId = history.pop();
      stopAnswerAudio();
      render();
    });
    next.addEventListener('click', () => {
      const scene = sceneMap.get(currentId);
      if (scene.kind === 'ending') {
        history = [];
        currentId = story.start_scene_id;
        render();
      } else if (scene.next_scene_id) goTo(scene.next_scene_id, true);
    });
    pause.addEventListener('click', () => {
      if (!paused) {
        paused = true;
        if (audio) audio.pause();
        if ('speechSynthesis' in window) window.speechSynthesis.pause();
        pause.textContent = '▶ Resume';
      } else {
        paused = false;
        if (audio) audio.play().catch(() => {});
        if ('speechSynthesis' in window) window.speechSynthesis.resume();
        pause.textContent = '⏸ Pause';
      }
    });
    questionInput.addEventListener('focus', () => {
      if (!paused) pause.click();
    });
    questions.addEventListener('submit', async (event) => {
      event.preventDefault();
      const text = questionInput.value.trim();
      if (!text || !askHandler || waitingAnswer) return;
      const scene = sceneMap.get(currentId);
      waitingAnswer = true;
      stopSpeech();
      stopAnswerAudio();
      paused = true;
      pause.textContent = '▶ Resume';
      ask.disabled = true;
      answerBox.hidden = false;
      answerText.textContent = 'Looking up your answer…';
      const askedSceneId = currentId;
      try {
        const result = await askHandler({
          case_id: story.case_id,
          question: text,
          scene_title: scene.headline,
          scene_metric: scene.metric_badge ? scene.metric_badge.value : '',
          scene_narration: scene.narration
        });
        if (destroyed || currentId !== askedSceneId) return;
        answerText.textContent = safeText(result && result.answer ? result.answer : 'No answer available.');
        if (result && result.audio_b64) {
          answerAudio = new Audio('data:audio/mpeg;base64,' + result.audio_b64);
          answerAudio.play().catch(() => {});
        } else if ('speechSynthesis' in window && result && result.answer) {
          const u = new SpeechSynthesisUtterance(result.answer);
          u.lang = 'en-US';
          window.speechSynthesis.speak(u);
        }
      } catch (error) {
        if (!destroyed && currentId === askedSceneId) answerText.textContent = 'Could not resolve your question: ' + safeText(error.message);
      } finally {
        waitingAnswer = false;
        ask.disabled = false;
      }
    });
    continueAfterAsk.addEventListener('click', () => {
      stopAnswerAudio();
      render();
    });

    render();
    return {
      destroy() {
        destroyed = true;
        stopSpeech();
        stopAnswerAudio();
        container.replaceChildren();
      },
      goToScene(sceneId) { goTo(sceneId, true); },
      getCurrentSceneId() { return currentId; }
    };
  }
  window.SherpasVideo = { mount };
})();