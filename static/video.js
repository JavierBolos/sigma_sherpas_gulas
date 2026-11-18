/* SHERPAS · Reproductor audiovisual interactivo · Contrato JSON v1.0
 * API pública: window.SherpasVideo.mount({ container, story, onAsk })
 * No consulta MCP ni modifica el plan: muestra el JSON entregado por el backend.
 */
(function () {
  'use strict';

  const safeText = (value) => String(value ?? '');
  const svgNamespace = 'http://www.w3.org/2000/svg';
  const make = (tag, className, text) => {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = safeText(text);
    return el;
  };
  const makeSvgElement = (tag, attributes) => {
    const el = document.createElementNS(svgNamespace, tag);
    for (const [name, value] of Object.entries(attributes || {})) el.setAttribute(name, value);
    return el;
  };

  function validateStory(story) {
    if (!story || story.schema_version !== '1.0' || !Array.isArray(story.scenes)) {
      throw new Error('Se necesita una historia válida del contrato JSON v1.0.');
    }
    const sceneMap = new Map();
    for (const scene of story.scenes) {
      if (!scene.id || sceneMap.has(scene.id)) throw new Error('Hay escenas sin identificador o duplicadas.');
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
    const timeline = make('div', 'sv-timeline');
    const stage = make('main', 'sv-stage');
    const motion = make('div', 'sv-motion');
    motion.setAttribute('aria-hidden', 'true');
    const year = make('div', 'sv-year');
    const symbol = make('div', 'sv-symbol');
    const title = make('h3', 'sv-scene-title');
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
    stage.append(motion, year, symbol, title, metric, narration, source, choices, answerBox);

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

    top.append(eyebrow, storyTitle, disclaimer, step, timeline);
    device.append(top, stage, controls, questions);
    root.append(device);
    container.append(root);

    const visuals = { family: '👨‍👩‍👧‍👦', timeline: '🗓️', chart: '📈', goal: '🎓', summary: '✨', choice: '🧭' };

    function renderMotion(scene) {
      const type = Object.prototype.hasOwnProperty.call(visuals, scene.visual_type) ? scene.visual_type : 'summary';
      motion.className = 'sv-motion sv-motion-' + type;
      const svg = makeSvgElement('svg', { viewBox: '0 0 460 340', preserveAspectRatio: 'xMidYMid slice' });
      motion.replaceChildren(svg);
      const add = (tag, attributes, parent) => {
        const el = makeSvgElement(tag, attributes);
        (parent || svg).append(el);
        return el;
      };

      if (type === 'family') {
        [100, 190, 280].forEach((x, index) => {
          const person = add('g', { class: 'sv-visual-person sv-visual-person-' + (index + 1), transform: 'translate(' + x + ' 0)' });
          add('circle', { class: 'sv-visual-head', cx: '0', cy: index === 1 ? '188' : '198', r: index === 1 ? '19' : '16' }, person);
          add('path', { class: 'sv-visual-body', d: index === 1 ? 'M-28 282 Q-24 220 0 218 Q24 220 28 282Z' : 'M-25 282 Q-22 230 0 228 Q22 230 25 282Z' }, person);
        });
      } else if (type === 'chart') {
        add('path', { class: 'sv-visual-line', d: 'M58 282 H405 M58 70 V282' });
        [75, 120, 166, 212, 258, 304, 350].forEach((x, index) => add('rect', {
          class: 'sv-visual-bar sv-visual-bar-' + (index + 1), x: String(x), y: String(248 - index * 22), width: '25', height: String(34 + index * 22), rx: '7'
        }));
        add('path', { class: 'sv-visual-trend', d: 'M82 220 C135 208 145 185 174 190 S223 146 258 154 S322 94 362 92' });
        add('circle', { class: 'sv-visual-point', cx: '362', cy: '92', r: '8' });
      } else if (type === 'goal') {
        add('circle', { class: 'sv-visual-sun', cx: '348', cy: '94', r: '36' });
        add('path', { class: 'sv-visual-hill sv-visual-hill-back', d: 'M0 282 L130 170 L235 282Z' });
        add('path', { class: 'sv-visual-hill sv-visual-hill-front', d: 'M125 282 L285 132 L460 282Z' });
        add('path', { class: 'sv-visual-flagpole', d: 'M285 132 V76' });
        add('path', { class: 'sv-visual-flag', d: 'M285 77 H326 L311 91 H285Z' });
      } else if (type === 'timeline') {
        add('path', { class: 'sv-visual-route', d: 'M36 232 C100 154 144 284 207 196 S322 116 425 164' });
        [[36, 232], [142, 223], [244, 171], [342, 137], [425, 164]].forEach((point, index) => {
          add('circle', { class: 'sv-visual-stop sv-visual-stop-' + (index + 1), cx: String(point[0]), cy: String(point[1]), r: '11' });
        });
      } else if (type === 'choice') {
        add('path', { class: 'sv-visual-branch', d: 'M230 82 V166 M230 166 C230 218 105 202 105 276 M230 166 C230 218 355 202 355 276' });
        [[230, 82], [105, 276], [355, 276]].forEach((point, index) => add('circle', {
          class: 'sv-visual-node sv-visual-node-' + (index + 1), cx: String(point[0]), cy: String(point[1]), r: index ? '19' : '24'
        }));
      } else {
        add('circle', { class: 'sv-visual-orbit sv-visual-orbit-one', cx: '230', cy: '176', r: '58' });
        add('circle', { class: 'sv-visual-orbit sv-visual-orbit-two', cx: '230', cy: '176', r: '103' });
        add('circle', { class: 'sv-visual-orbit sv-visual-orbit-three', cx: '230', cy: '176', r: '148' });
        [[230, 28], [372, 176], [230, 324], [88, 176]].forEach((point, index) => add('circle', {
          class: 'sv-visual-star sv-visual-star-' + (index + 1), cx: String(point[0]), cy: String(point[1]), r: '7'
        }));
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
      stage.classList.remove('is-paused');
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
    function showTimeline(scene) {
      timeline.replaceChildren();
      const items = history.map((id) => sceneMap.get(id)).concat(scene);
      for (const [i, item] of items.entries()) {
        const label = item.year === null ? item.period_label : String(item.year);
        const node = make('span', 'sv-timeline-dot' + (i === items.length - 1 ? ' is-current' : ''), label);
        timeline.append(node);
      }
      step.textContent = scene.kind === 'choice' ? 'TÚ ELIGES EL RECORRIDO' : scene.kind === 'ending' ? 'EL SIGUIENTE PASO' : 'UN MOMENTO DE VUESTRA HISTORIA';
    }
    function render() {
      const scene = sceneMap.get(currentId);
      answerBox.hidden = true;
      waitingAnswer = false;
      questionInput.value = '';
      stage.classList.remove('is-paused');
      renderMotion(scene);
      year.textContent = scene.year === null ? safeText(scene.period_label) : String(scene.year);
      symbol.textContent = visuals[scene.visual_type] || '✨';
      title.textContent = safeText(scene.title);
      narration.textContent = safeText(scene.narration);
      metric.hidden = !scene.metric;
      if (scene.metric) {
        metricLabel.textContent = safeText(scene.metric.label);
        metricValue.textContent = safeText(scene.metric.value);
      }
      source.textContent = scene.metric && scene.metric.source_ref ? 'Fuente: ' + safeText(scene.metric.source_ref) : '';
      source.hidden = !source.textContent;
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
      pause.disabled = false;
      questions.hidden = !askHandler;
      if (story.data_status === 'mock') root.classList.add('sv-is-mock');
      else root.classList.remove('sv-is-mock');
      showTimeline(scene);
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
        stage.classList.add('is-paused');
        if ('speechSynthesis' in window) window.speechSynthesis.pause();
        pause.textContent = '▶ Reanudar';
      } else {
        paused = false;
        if (audio) audio.play().catch(() => {});
        stage.classList.remove('is-paused');
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
      stage.classList.add('is-paused');
      pause.textContent = '▶ Reanudar';
      ask.disabled = true;
      answerBox.hidden = false;
      answerText.textContent = 'Consultando la explicación…';
      const askedSceneId = currentId;
      try {
        const result = await askHandler({
          case_id: story.case_id,
          question: text,
          scene_title: scene.title,
          scene_metric: scene.metric ? scene.metric.value : '',
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
