
/* SHERPAS · Interactive Audiovisual Player · Annual Escalation & Video Edition
- Public API: window.SherpasVideo.mount({ container, story, onAsk, onSceneChange })
- Visualizes year-by-year financial escalation, scene videos, and unlocks the tracker on ending.
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

  // Biblioteca: clips disponibles ahora y clips financieros que podréis añadir después.
  // Los nombres deben coincidir EXACTAMENTE con los archivos de static/videos/.
  const VIDEO_DIR = '/static/videos/';
  const EMOTIONAL = {
    family: 'familia_feliz.mp4',
    personal: 'persona_planificando.mp4',
    familyDecisions: 'mesa_decisiones.mp4',
    vacation: 'vacaciones.mp4',
    home: 'nuevo_hogar.mp4',
    car: 'movilidad_vehiculo.mp4',
    university: 'universidad.mp4',
    time: 'paso_del_tiempo.mp4',
    retirement: 'vida_jubilacion.mp4',
    emergency: 'gastos_imprevistos.mp4'
  };

  // Primer archivo: específico. Los siguientes son alternativas si aún no lo habéis generado.
  // Así la app funciona con vuestros 10 MP4 actuales y mejora al añadir los demás.
  const VIDEO_RULES = [
    { match: /universidad|universitar|educacion|estudi|college|tuition|scholar|529|matricula|hijos.*futuro|children.*education/, clips: ['ahorro_educacion.mp4', EMOTIONAL.university] },
    { match: /viaje|vacacion|travel|holiday|trip|tourism|leisure/, clips: [EMOTIONAL.vacation] },
    { match: /coche|vehicul|automovil|car purchase|car loan|vehicle|auto loan|mobility/, clips: [EMOTIONAL.car] },
    { match: /vivienda|casa|hogar|hipoteca|mortgage|housing|home purchas|buy a home|new home|property purchas/, clips: [EMOTIONAL.home] },
    { match: /seguro|proteccion|cobertura|insurance|umbrella|liability|life cover|protection/, clips: ['cobertura_seguros.mp4', EMOTIONAL.emergency] },
    { match: /emergencia|imprevist|emergency fund|cash reserve|rainy.day|safety cushion|liquidity buffer|reserve target/, clips: ['reserva_emergencia.mp4', EMOTIONAL.emergency] },
    { match: /tarjeta|intereses|credit card|interest rate|high.interest|apr|costly debt/, clips: ['coste_intereses.mp4', EMOTIONAL.familyDecisions] },
    { match: /amortiza|deuda|prestamo|debt|loan|liabilit|repayment|debt.free/, clips: ['amortizacion_deuda.mp4', EMOTIONAL.familyDecisions] },
    { match: /ingresos.*gastos|flujo de caja|cash flow|income.*expenses|sankey|monthly budget|presupuesto|income.*spend/, clips: ['flujo_dinero.mp4', EMOTIONAL.familyDecisions] },
    { match: /ahorro periodico|contribucion|aportacion|401\s?\(?k\)?|retirement accounts|employer match|hsa|ira|savings contribution/, clips: ['aportaciones_ahorro.mp4', EMOTIONAL.familyDecisions] },
    { match: /asignacion|cartera|asset allocation|portfolio mix|allocation|rebalanc|stock.*bond/, clips: ['distribucion_cartera.mp4', EMOTIONAL.familyDecisions] },
    { match: /volatilidad|rentabilidad|benchmark|risk.*return|volatility|market performance|market shock|drawdown|riesgo/, clips: ['riesgo_rendimiento.mp4', EMOTIONAL.familyDecisions] },
    { match: /patrimonio neto|net worth|activos|pasivos|assets|liabilities|balance sheet/, clips: ['activos_pasivos.mp4', EMOTIONAL.familyDecisions] },
    { match: /retiro|jubilacion|retirement|pension|social security|retire|pensionist/, clips: ['ingresos_jubilacion.mp4', EMOTIONAL.retirement] },
    { match: /financiar|funding|objetivos|goals|prioridades|priorit|decision|trade.off|recommendation|recomendacion/, clips: ['decisiones_presupuesto.mp4', EMOTIONAL.familyDecisions] }
  ];

  function normalizar(text) {
    return String(text ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }

  function videoCandidates(scene, story) {
    const list = [];
    const push = (...clips) => {
      for (const clip of clips) {
        if (!clip) continue;
        const url = clip.startsWith('/') ? clip : VIDEO_DIR + clip;
        // No se aceptan rutas arbitrarias del texto generado por la IA.
        if (/^\/static\/videos\/[a-z0-9_-]+\.mp4$/i.test(url) && !list.includes(url)) list.push(url);
      }
    };

    // Si el backend asigna un MP4 local a una escena, tiene preferencia.
    if (scene.video_url) push(scene.video_url);
    if (scene.video_key) push(scene.video_key.endsWith('.mp4') ? scene.video_key : scene.video_key + '.mp4');

    // La introducción puede variar según el perfil real.
    const isIntro = scene.id === story.start_scene_id || /^(starting_point|intro|introduction)$/.test(scene.id);
    if (isIntro) {
      if (story.case_id === 'timothy-melanie-weah' || story.case_id === 'daniel-emily-johnson') {
        push(EMOTIONAL.family);
      } else if (story.case_id === 'samantha-lewis') {
        push('adulto_con_hijos.mp4', EMOTIONAL.personal);
      } else {
        push(EMOTIONAL.personal);
      }
      push(EMOTIONAL.familyDecisions);
      return list;
    }

    if (scene.kind === 'choice') {
      push('decisiones_presupuesto.mp4', EMOTIONAL.familyDecisions);
      return list;
    }
    if (scene.kind === 'ending') {
      push('futuro_abierto.mp4', EMOTIONAL.time, EMOTIONAL.familyDecisions);
      return list;
    }
    if (scene.id === 'plan_projection') {
      push('proyeccion_patrimonio.mp4', EMOTIONAL.time);
    }

    // Título e indicador tienen más peso que una mención secundaria.
    const main = normalizar([scene.headline, scene.metric_badge?.label, scene.period_label].join(' '));
    const secondary = normalizar(scene.narration);
    const ranked = VIDEO_RULES.map((r, index) => ({
      ...r,
      index,
      score: Math.min(
        (r.match.test(main) ? 5 : 0) + (r.match.test(secondary) ? 1 : 0),
        index === VIDEO_RULES.length - 1 ? 3 : 6
      )
    })).filter(r => r.score > 0).sort((a,b) => b.score - a.score || a.index - b.index);

    for (const r of ranked.slice(0, 2)) push(...r.clips);

    if (scene.id === 'plan_projection' || /proyeccion|projection|forecast|timeline|horizon|future/.test(main)) {
      push('proyeccion_patrimonio.mp4', EMOTIONAL.time);
    }

    if (scene.visual_theme === 'dream_home') push(EMOTIONAL.home);
    if (scene.visual_theme === 'early_retirement') push('proyeccion_patrimonio.mp4', EMOTIONAL.retirement);
    if (scene.visual_theme === 'financial_shield') push('cobertura_seguros.mp4', EMOTIONAL.emergency);
    if (scene.visual_theme === 'family_travel') push(EMOTIONAL.vacation);

    push(EMOTIONAL.familyDecisions);
    return list;
  }

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
    
    ladderStrip.style.cssText = 'display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;width:100%;margin-top:14px;align-items:stretch;';
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

    // Scene 16:9 Background/Illustration Video
    const bgVideo = document.createElement('video');
    bgVideo.className = 'sv-scene-video';
    bgVideo.muted = true;
    bgVideo.loop = true;
    bgVideo.playsInline = true;
    bgVideo.autoplay = true;
    bgVideo.preload = 'auto';
    bgVideo.hidden = true;
    bgVideo.setAttribute('aria-hidden', 'true');
    bgVideo.disablePictureInPicture = true;
    bgVideo.controls = false;
    let candidates = [];
    let candidateIndex = 0;

    function showCandidate() {
      if (destroyed) return;
      if (candidateIndex >= candidates.length) {
        bgVideo.pause();
        bgVideo.hidden = true;
        bgVideo.removeAttribute('src');
        symbol.hidden = false;
        return;
      }
      bgVideo.hidden = true;
      symbol.hidden = false;
      bgVideo.src = candidates[candidateIndex];
      bgVideo.load();
    }

    bgVideo.addEventListener('loadeddata', () => {
      if (destroyed || candidateIndex >= candidates.length) return;
      bgVideo.hidden = false;
      symbol.hidden = true;
      if (!paused && !waitingAnswer) bgVideo.play().catch(() => {});
    });

    // Si un vídeo no existe, intentar el siguiente.
    bgVideo.addEventListener('error', () => {
      if (destroyed) return;
      candidateIndex += 1;
      showCandidate();
    });

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
    stage.append(year, bgVideo, symbol, headline, metric, narration, source, choices, answerBox);

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

      // Selección automática de clip según el contenido de la escena.
      bgVideo.pause();
      candidates = videoCandidates(scene, story);
      candidateIndex = 0;
      showCandidate();

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
        bgVideo.pause();
        if ('speechSynthesis' in window) window.speechSynthesis.pause();
        pause.textContent = '▶ Resume';
      } else {
        paused = false;
        if (audio) audio.play().catch(() => {});
        if (!bgVideo.hidden) bgVideo.play().catch(() => {});
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
      bgVideo.pause();
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
        if (!destroyed && currentId === askedSceneId) {
          answerText.textContent = 'Could not resolve your question: ' + safeText(error.message);
        }
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
        bgVideo.pause();
        bgVideo.removeAttribute('src');
        container.replaceChildren();
      },
      goToScene(sceneId) { goTo(sceneid, true); },
      getCurrentSceneId() { return currentId; }
    };
  }

  window.SherpasVideo = {
    mount,
    elegirVideo: (scene, story = {}) =>
      videoCandidates(
        scene,
        { start_scene_id: story.start_scene_id || 'starting_point', ...story }
      )[0] || null
  };
})();
