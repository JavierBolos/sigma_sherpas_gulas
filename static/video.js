/* SHERPAS · Reproductor audiovisual interactivo · Contrato JSON v1.0
 * API pública: window.SherpasVideo.mount({ container, story, onAsk })
 * No consulta MCP ni modifica el plan: muestra el JSON entregado por el backend.
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
    if (!story || story.schema_version !== '1.0' || !Array.isArray(story.scenes) || story.scenes.length !== 4) {
      throw new Error('Se necesita una historia válida del contrato JSON v1.0.');
    }
    const sceneMap = new Map();
    for (const scene of story.scenes) {
      if (!scene.id || sceneMap.has(scene.id)) throw new Error('Hay escenas sin identificador o duplicadas.');
      if (!THEMES.has(scene.visual_theme) || !scene.headline || !scene.narration || !scene.metric_badge) {
        throw new Error('Cada escena debe incluir tema, titular, narración e indicador.');
      }
      sceneMap.set(scene.id, scene);
    }
    if (!sceneMap.has(story.start_scene_id)) throw new Error('No existe la escena inicial.');
    for (const scene of story.scenes) {
      if (scene.next_scene_id && !sceneMap.has(scene.next_scene_id)) throw new Error(`Escena inexistente: ${scene.next_scene_id}`);
      for (const choice of (scene.choices || [])) {
        if (!sceneMap.has(choice.next_scene_id)) throw new Error(`Ruta inexistente: ${choice.next_scene_id}`);
      }
    }
    return sceneMap;
  }

  function mount({ container, story, onAsk } = {}) {
    if (!(container instanceof HTMLElement)) throw new Error('container debe ser un elemento HTML.');
    const sceneMap = validateStory(story);
    const askHandler = typeof onAsk === 'function' ? onAsk : null;
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
    root.setAttribute('aria-label', 'Historia financiera interactiva');
    const device = make('div', 'sv-device');
    const top = make('header', 'sv-header');
    const eyebrow = make('div', 'sv-eyebrow', 'SHERPAS · TU HISTORIA');
    const storyTitle = make('h2', 'sv-story-title', story.title);
    const disclaimer = make('p', 'sv-disclaimer', story.disclaimer);
    const step = make('div', 'sv-step', '');
    const progressTrack = make('div', 'sv-progress-track');
    progressTrack.setAttribute('role', 'progressbar');
    progressTrack.setAttribute('aria-label', 'Progreso de la historia');
    progressTrack.setAttribute('aria-valuemin', '1');
    progressTrack.setAttribute('aria-valuemax', String(story.scenes.length));
    const progressFill = make('div', 'sv-progress-fill');
    progressTrack.append(progressFill);
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
    const continueAfterAsk = make('button', 'sv-btn sv-answer-next', '↻ Volver a escuchar esta escena');
    answerBox.append(answerText, continueAfterAsk);
    stage.append(year, symbol, headline, metric, narration, source, choices, answerBox);

    const controls = make('div', 'sv-controls');
    const back = make('button', 'sv-btn sv-muted', '← Atrás');
    const pause = make('button', 'sv-btn sv-muted', '⏸ Pausar');
    const next = make('button', 'sv-btn sv-primary', 'Siguiente →');
    controls.append(back, pause, next);

    const questions = make('form', 'sv-qa');
    const questionLabel = make('label', 'sv-qa-label', '¿Alguna duda sobre esta escena?');
    const questionInput = make('input', 'sv-qa-input');
    questionInput.type = 'text';
    questionInput.placeholder = 'Ej.: ¿Qué significa esta cifra?';
    questionInput.maxLength = 500;
    questionInput.autocomplete = 'off';
    questionLabel.htmlFor = 'sv-question-' + Math.random().toString(36).slice(2, 8);
    questionInput.id = questionLabel.htmlFor;
    const ask = make('button', 'sv-btn sv-ask', 'Preguntar');
    ask.type = 'submit';
    questions.append(questionLabel, questionInput, ask);

    top.append(eyebrow, storyTitle, disclaimer, step, progressTrack);
    device.append(top, stage, controls, questions);
    root.append(device);
    container.append(root);

    const visuals = {
      family_travel: '✈️',
      dream_home: '🏡',
      early_retirement: '🌅',
      financial_shield: '🛡️'
    };

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
      pause.textContent = '⏸ Pausar';
      const thisPlayback = playbackId;
      const finished = () => {
        if (destroyed || paused || thisPlayback !== playbackId || waitingAnswer) return;
        if (scene.kind === 'narration' && scene.next_scene_id) goTo(scene.next_scene_id, true);
      };
      if (scene.audio_b64) {
        audio = new Audio('data:audio/mpeg;base64,' + scene.audio_b64);
        audio.onended = finished;
        audio.play().catch(() => { /* Controles manuales disponibles */ });
      } else if ('speechSynthesis' in window && scene.narration) {
        utterance = new SpeechSynthesisUtterance(scene.narration);
        utterance.lang = 'es-ES';
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
      progressTrack.setAttribute('aria-valuetext', `Escena ${currentStep} de ${story.scenes.length}`);
      step.textContent = `ESCENA ${currentStep} DE ${story.scenes.length}`;
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
        ? 'Fuente: ' + safeText(scene.metric_badge.source_ref)
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
      next.textContent = scene.kind === 'ending' ? '↻ Volver al inicio' : 'Siguiente →';
      pause.disabled = !scene.narration;
      questions.hidden = !askHandler;
      if (story.data_status === 'mock') root.classList.add('sv-is-mock');
      else root.classList.remove('sv-is-mock');
      speak(scene);
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
        pause.textContent = '▶ Reanudar';
      } else {
        paused = false;
        if (audio) audio.play().catch(() => {});
        if ('speechSynthesis' in window) window.speechSynthesis.resume();
        pause.textContent = '⏸ Pausar';
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
      pause.textContent = '▶ Reanudar';
      ask.disabled = true;
      answerBox.hidden = false;
      answerText.textContent = 'Consultando la explicación…';
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
        answerText.textContent = safeText(result && result.answer ? result.answer : 'No hay respuesta disponible.');
        if (result && result.audio_b64) {
          answerAudio = new Audio('data:audio/mpeg;base64,' + result.audio_b64);
          answerAudio.play().catch(() => {});
        } else if ('speechSynthesis' in window && result && result.answer) {
          const u = new SpeechSynthesisUtterance(result.answer);
          u.lang = 'es-ES';
          window.speechSynthesis.speak(u);
        }
      } catch (error) {
        if (!destroyed && currentId === askedSceneId) answerText.textContent = 'No se pudo resolver la duda: ' + safeText(error.message);
      } finally {
        waitingAnswer = false;
        ask.disabled = false;
      }
    });
    continueAfterAsk.addEventListener('click', () => {
      // La escena pausada se reproduce otra vez, NUNCA se salta automáticamente.
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
