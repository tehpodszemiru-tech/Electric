/* ============================================================
   3D-КАЛЬКУЛЯТОР «ДОМОВОЙ»
   Расчёт инженерных сетей + Three.js-визуализация + заявка.
   Загружается только на главной странице (index.html).
   ============================================================ */
(function () {
  'use strict';

  var section = document.getElementById('calculator-section');
  if (!section) return;

  var METRIKA_ID = 112788163;
  var LEAD_ENDPOINT = 'https://leads.vim-scrum.ru/lead';
  var TURNSTILE_SITEKEY = '0x4AAAAAAE665h3_Qwk-fPE_';
  var TG_URL = 'https://t.me/i_modelirovanie';
  var MAX_URL = 'https://max.ru/u/f9LHodD0cOIsupLRSocjx97vuftzHw1CE05LYTNe4o6ek7inmTIoqqN1PC0';
  var PHONE_DISPLAY = '+7 (993) 466-05-55';
  var STORAGE_KEY = 'domovoyCalcParamsV2';

  var WIDTH_MIN = 6;
  var WIDTH_MAX = 16;
  var WIDTH_STEP = 0.5;
  var LENGTH_MIN = 6;
  var LENGTH_MAX = 20;
  var LENGTH_STEP = 0.5;
  var HEIGHT_MIN = 2.5;
  var HEIGHT_MAX = 3.5;
  var HEIGHT_STEP = 0.1;

  var BOILER_POWERS = [12, 15, 20, 24, 28, 32, 36, 40, 50];

  var WALL_LABELS = {
    frame: 'Каркасный / СИП',
    block: 'Газобетон / Блок',
    brick: 'Кирпич / Монолит'
  };
  var WALL_HOUSE = {
    frame: 'каркасный дом',
    block: 'дом из газобетона',
    brick: 'кирпичный дом'
  };
  var WALL_3D_COLORS = {
    frame: 0x66788f,
    block: 0x8b9aad,
    brick: 0x9c7c6b
  };
  var WALL_MULT = {
    frame: 1.05,
    block: 1.16,
    brick: 1.28
  };

  var PRESETS = {
    compact: { width: 9, length: 10, height: 2.8, floors: 1, wall: 'frame', baths: 1 },
    family: { width: 10, length: 14, height: 2.9, floors: 1, wall: 'block', baths: 2 },
    cottage: { width: 10, length: 9, height: 3.0, floors: 2, wall: 'brick', baths: 3 }
  };

  var state = {
    format: 'turnkey', // project | turnkey
    width: 9,          // 6..16 м, шаг 0.5
    length: 10,        // 6..20 м, шаг 0.5
    height: 2.8,       // 2.5..3.5 м, шаг 0.1
    floors: 1,         // 1 | 2
    heating1: 'floor', // floor | radiators
    heating2: 'floor', // floor | radiators (только для 2 этажей)
    boiler: 'gas',     // gas | electric | wood | none
    wall: 'frame',     // frame | block | brick
    baths: 1,          // 1 | 2 | 3
    systems: { electric: true, heating: true, water: true },
    xray: true,
    autoRotate: false,
    unlocked: false,
    lead: { name: '', contact: '', channel: 'Telegram' }
  };

  var lastCalc = null;
  var calcParamsLoaded = false;

  /* ------------------------------------------------------------
     Утилиты
     ------------------------------------------------------------ */
  function $(id) { return document.getElementById(id); }

  function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }

  function snap(value, min, max, step) {
    var n = Number(value);
    if (!Number.isFinite(n)) return min;
    var snapped = Math.round((n - min) / step) * step + min;
    return clamp(Math.round(snapped * 100) / 100, min, max);
  }

  function num(v) {
    var n = Number(v);
    return Number.isFinite(n) ? n : 0;
  }

  var rubFormatter = new Intl.NumberFormat('ru-RU');

  function formatRub(value) {
    return rubFormatter.format(Math.round(value)) + ' ₽';
  }

  function reachGoal(goal) {
    try {
      if (typeof window.ym === 'function') {
        window.ym(METRIKA_ID, 'reachGoal', goal);
      }
    } catch (e) { /* Метрика может быть заблокирована */ }
  }

  function floorLabel() {
    if (state.floors === 2) return '2 этажа';
    return '1 этаж';
  }

  function levelCount() {
    return state.floors === 2 ? 2 : 1;
  }

  function formatLabel() {
    return state.format === 'project'
      ? 'Только проект (вся РФ)'
      : 'Проект + монтаж под ключ (Самара и обл.)';
  }

  function boilerLabel() {
    if (state.boiler === 'gas') return 'газовый';
    if (state.boiler === 'wood') return 'дровяной';
    if (state.boiler === 'electric') return 'электрический';
    return 'без котла';
  }

  function areaOf(width, length, floors) {
    var factor = floors === 2 ? 2 : 1;
    return Math.round(width * length * factor);
  }

  function perimeterOf(width, length) {
    return 2 * (width + length);
  }

  function formatMeters(value) {
    var rounded = Math.round(value * 10) / 10;
    return String(rounded).replace('.', ',') + ' м';
  }

  function plural(n, forms) {
    var abs = Math.abs(n) % 100;
    var last = abs % 10;
    if (abs > 10 && abs < 20) return forms[2];
    if (last > 1 && last < 5) return forms[1];
    if (last === 1) return forms[0];
    return forms[2];
  }

  function boilerPowerFor(area) {
    var raw = area * 0.1 + 3;
    for (var i = 0; i < BOILER_POWERS.length; i++) {
      if (BOILER_POWERS[i] >= raw) return BOILER_POWERS[i];
    }
    return BOILER_POWERS[BOILER_POWERS.length - 1];
  }

  function formatDim(value) {
    var rounded = Math.round(value * 10) / 10;
    return String(rounded).replace('.', ',');
  }

  function syncSlider(sliderId, numId, value, min, max) {
    var slider = $(sliderId);
    if (slider) {
      if (Number(slider.value) !== value) slider.value = value;
      var pct = ((value - min) / (max - min)) * 100;
      slider.style.setProperty('--calc-fill', pct.toFixed(2) + '%');
    }
    var numEl = $(numId);
    if (numEl && Number(numEl.value) !== value) numEl.value = value;
  }

  /* ------------------------------------------------------------
     Расчётная модель «Домовой»
     ------------------------------------------------------------ */
  function calculate() {
    var width = state.width;
    var length = state.length;
    var height = state.height;
    var area = areaOf(width, length, state.floors);
    var perimeter = perimeterOf(width, length);
    var floorArea = Math.round(width * length);
    var floors = state.floors;
    var wallMult = WALL_MULT[state.wall] || 1;
    var levels = levelCount();
    var bathrooms = state.baths;
    var systems = state.systems;
    var heightMult = 1 + (height - HEIGHT_MIN) * 0.08;

    var activeCount = (systems.electric ? 1 : 0) +
                      (systems.heating ? 1 : 0) +
                      (systems.water ? 1 : 0);

    // 1. Электрика
    var cable25 = 0;
    var cable15 = 0;
    var shieldModules = 0;
    var elPoints = 0;
    var sockets = 0;
    var lights = 0;
    var switches = 0;
    var outputs = 0;
    var elMat = 0;
    var elWork = 0;

    if (systems.electric) {
      var rooms = Math.max(3, Math.round(area / 18));
      sockets = Math.round(area * 0.18) + 6 + bathrooms * 2;
      lights = Math.round(area * 0.12) + rooms;
      switches = rooms + bathrooms;
      outputs = 4 + (levels === 2 ? 2 : 0);
      elPoints = sockets + lights + switches + outputs;

      var wallCableMult = state.wall === 'brick' ? 1.14 : (state.wall === 'block' ? 1.06 : 1);
      cable25 = Math.round((area * 2.0 + perimeter * 1.2 + levels * 22) * wallCableMult * heightMult);
      cable15 = Math.round((area * 1.3 + perimeter * 0.6 + levels * 16) * heightMult);

      var rawModules = 16 + Math.ceil(area / 20) * 2 + bathrooms * 2 + (systems.heating ? 4 : 0);
      var standardShields = [24, 36, 48, 54, 72];
      shieldModules = standardShields.find(function (s) { return s >= rawModules; }) || 72;

      elMat = Math.round(cable25 * 115 + cable15 * 75 + shieldModules * 680 + elPoints * 190);
      elWork = Math.round((elPoints * 650 + shieldModules * 380 + area * 140) * wallMult);
    }

    // 2. Отопление: тёплый пол / радиаторы по этажам + котёл
    var floorPipe = 0;
    var heatLoops = 0;
    var heatMat = 0;
    var heatWork = 0;
    var underfloorArea = 0;
    var underfloorFloors = 0;
    var radiators = 0;
    var radPipe = 0;
    var radMat = 0;
    var radWork = 0;
    var boilerPowerKw = 0;
    var boilerMat = 0;
    var boilerWork = 0;

    if (systems.heating) {
      var underfloorFactor = floors === 2 ? 0.76 : 0.82;
      var floorTypes = [state.heating1];
      if (floors === 2) floorTypes.push(state.heating2);

      floorTypes.forEach(function (type) {
        if (type === 'radiators') {
          radiators += 4;
        } else {
          underfloorArea += Math.round(floorArea * underfloorFactor);
          underfloorFloors += 1;
        }
      });

      if (underfloorArea > 0) {
        floorPipe = Math.round(underfloorArea * 5.6);
        heatLoops = Math.max(3, Math.ceil(floorPipe / 75));
        heatMat = Math.round(floorPipe * 78 + heatLoops * 3400 + 9500);
        heatWork = Math.round((underfloorArea * 360 + heatLoops * 1900) * (underfloorFloors === 2 ? 1.12 : 1));
      }

      if (radiators > 0) {
        radPipe = Math.round(radiators * 6 + perimeter * 0.35 + 12);
        radMat = Math.round(radiators * 9500 + radPipe * 170 + 4500);
        radWork = Math.round((radiators * 4500 + radPipe * 120) * wallMult);
        heatMat += radMat;
        heatWork += radWork;
      }

      if (state.boiler !== 'none') {
        boilerPowerKw = boilerPowerFor(area);
        if (state.boiler === 'gas') {
          boilerMat = Math.round(70000 + boilerPowerKw * 1800 + 20000);
          boilerWork = 35000;
        } else if (state.boiler === 'wood') {
          boilerMat = Math.round(60000 + boilerPowerKw * 1500 + 25000);
          boilerWork = 35000;
        } else {
          boilerMat = Math.round(35000 + boilerPowerKw * 1200 + 10000);
          boilerWork = 25000;
        }
        heatMat += boilerMat;
        heatWork += boilerWork;
      }
    }

    // 3. Водоснабжение и канализация / септик
    var waterPipe = 0;
    var sewerPipe = 0;
    var waterMat = 0;
    var waterWork = 0;

    if (systems.water) {
      waterPipe = Math.round(18 + bathrooms * 16 + levels * 10 + area * 0.14 + perimeter * 0.1);
      sewerPipe = Math.round(10 + bathrooms * 7 + levels * 5 + perimeter * 0.05);

      waterMat = Math.round(waterPipe * 170 + sewerPipe * 340 + bathrooms * 5200 + 6000);
      waterWork = Math.round((bathrooms * 11500 + levels * 4500 + area * 75) * wallMult);
    }

    // 4. 3D-проект и спецификация в ПО «Домовой»
    var projectCost = activeCount === 0
      ? 0
      : Math.round(
          9000 + activeCount * 5500 + area * 145 +
          (floors === 2 ? 4500 : 0) + bathrooms * 1500 +
          (radiators > 0 ? 2500 + radiators * 200 : 0) +
          (systems.heating && state.boiler !== 'none' ? 3000 : 0)
        );

    var materialsTotal = elMat + heatMat + waterMat;
    var laborTotal = elWork + heatWork + waterWork;
    var total = state.format === 'project'
      ? projectCost
      : materialsTotal + laborTotal + projectCost;

    var rangeMin = total > 0 ? Math.round((total * 0.93) / 1000) * 1000 : 0;
    var rangeMax = total > 0 ? Math.round((total * 1.08) / 1000) * 1000 : 0;

    lastCalc = {
      width: width,
      length: length,
      height: height,
      area: area,
      perimeter: perimeter,
      heightMult: heightMult,
      floors: floors,
      floorArea: floorArea,
      wall: state.wall,
      baths: bathrooms,
      activeCount: activeCount,
      cable25: cable25,
      cable15: cable15,
      shieldModules: shieldModules,
      elPoints: elPoints,
      sockets: sockets,
      lights: lights,
      switches: switches,
      outputs: outputs,
      elMat: elMat,
      elWork: elWork,
      elSubtotal: elMat + elWork,
      floorPipe: floorPipe,
      heatLoops: heatLoops,
      underfloorArea: underfloorArea,
      underfloorFloors: underfloorFloors,
      radiators: radiators,
      radPipe: radPipe,
      radMat: radMat,
      radWork: radWork,
      boilerPowerKw: boilerPowerKw,
      boilerMat: boilerMat,
      boilerWork: boilerWork,
      heatMat: heatMat,
      heatWork: heatWork,
      heatSubtotal: heatMat + heatWork,
      waterPipe: waterPipe,
      sewerPipe: sewerPipe,
      waterMat: waterMat,
      waterWork: waterWork,
      waterSubtotal: waterMat + waterWork,
      materialsTotal: materialsTotal,
      laborTotal: laborTotal,
      projectCost: projectCost,
      total: total,
      rangeMin: rangeMin,
      rangeMax: rangeMax
    };

    return lastCalc;
  }

  /* ------------------------------------------------------------
     Обновление интерфейса
     ------------------------------------------------------------ */
  var rebuilding = false;

  function updateUI() {
    var calc = calculate();
    var isProject = state.format === 'project';

    // Верхняя строка стоимости
    var rangeEl = $('calc-range');
    if (rangeEl) {
      if (calc.activeCount === 0) {
        rangeEl.textContent = 'Выберите хотя бы одну инженерную сеть';
      } else {
        rangeEl.textContent = 'от ' +
          formatRub(calc.rangeMin) + ' до ' + formatRub(calc.rangeMax);
      }
    }

    var modeChip = $('calc-mode-chip');
    if (modeChip) modeChip.textContent = isProject ? 'Только проект (вся РФ)' : 'Проект + монтаж (Самара и обл.)';

    var summaryEl = $('calc-summary');
    if (summaryEl) {
      var scope = isProject ? 'Проект и спецификация' : 'Материалы + монтаж + 3D-проект';
      summaryEl.innerHTML =
        '<span>' + formatDim(calc.width) + ' × ' + formatDim(calc.length) + ' м</span>' +
        '<span>H ' + formatMeters(calc.height) + '</span>' +
        '<span>' + calc.area + ' м²</span>' +
        '<span>' + floorLabel() + '</span>' +
        '<span>' + WALL_LABELS[state.wall] + '</span>' +
        '<span>' + state.baths + ' с/у</span>' +
        '<span>' + scope + '</span>';
    }

    // Формат заказа
    section.querySelectorAll('[data-calc-format]').forEach(function (btn) {
      var active = btn.getAttribute('data-calc-format') === state.format;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });

    // Габариты дома
    var widthReadout = $('calc-width-readout');
    if (widthReadout) widthReadout.textContent = formatMeters(state.width);
    var lengthReadout = $('calc-length-readout');
    if (lengthReadout) lengthReadout.textContent = formatMeters(state.length);
    var heightReadout = $('calc-height-readout');
    if (heightReadout) heightReadout.textContent = formatMeters(state.height);

    syncSlider('calc-width', 'calc-width-num', state.width, WIDTH_MIN, WIDTH_MAX);
    syncSlider('calc-length', 'calc-length-num', state.length, LENGTH_MIN, LENGTH_MAX);
    syncSlider('calc-height', 'calc-height-num', state.height, HEIGHT_MIN, HEIGHT_MAX);

    setText('calc-area-out', calc.area + ' м²');
    setText('calc-perimeter-out', calc.perimeter + ' м');

    // Пресеты
    section.querySelectorAll('[data-calc-preset]').forEach(function (btn) {
      var preset = PRESETS[btn.getAttribute('data-calc-preset')];
      var active = !!preset &&
        preset.width === state.width &&
        preset.length === state.length &&
        preset.height === state.height &&
        preset.floors === state.floors &&
        preset.wall === state.wall &&
        preset.baths === state.baths;
      btn.classList.toggle('is-active', active);
    });

    // Этажность
    section.querySelectorAll('[data-calc-floors]').forEach(function (btn) {
      var v = btn.getAttribute('data-calc-floors');
      var active = (v === '2' && state.floors === 2) ||
                   (v === '1' && state.floors === 1);
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });

    // Материал стен
    section.querySelectorAll('[data-calc-wall]').forEach(function (btn) {
      var active = btn.getAttribute('data-calc-wall') === state.wall;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });

    // Санузлы
    section.querySelectorAll('[data-calc-bath]').forEach(function (btn) {
      var active = Number(btn.getAttribute('data-calc-bath')) === state.baths;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });

    // Отопление по этажам и котёл
    var heatingOn = !!state.systems.heating;
    var h1Group = $('calc-heating1-group');
    if (h1Group) h1Group.hidden = !heatingOn;
    var h2Group = $('calc-heating2-group');
    if (h2Group) h2Group.hidden = !heatingOn || state.floors !== 2;
    var boilerGroup = $('calc-boiler-group');
    if (boilerGroup) boilerGroup.hidden = !heatingOn;

    section.querySelectorAll('[data-calc-heating]').forEach(function (btn) {
      var parts = btn.getAttribute('data-calc-heating').split(':');
      var value = parts[0] === '1' ? state.heating1 : state.heating2;
      var active = value === parts[1];
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });

    section.querySelectorAll('[data-calc-boiler]').forEach(function (btn) {
      var active = btn.getAttribute('data-calc-boiler') === state.boiler;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });

    // Системы — слои 3D
    ['electric', 'heating', 'water'].forEach(function (key) {
      var on = !!state.systems[key];
      section.querySelectorAll('[data-calc-system="' + key + '"]').forEach(function (btn) {
        btn.classList.toggle('is-active', on);
        btn.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
    });

    // X-ray / авто-облёт
    section.querySelectorAll('[data-calc-xray]').forEach(function (btn) {
      btn.classList.toggle('is-active', state.xray);
      btn.setAttribute('aria-pressed', state.xray ? 'true' : 'false');
    });
    section.querySelectorAll('[data-calc-autorotate]').forEach(function (btn) {
      btn.classList.toggle('is-active', state.autoRotate);
      btn.setAttribute('aria-pressed', state.autoRotate ? 'true' : 'false');
    });

    // Телеметрия под 3D
    var telEl = $('calc-tel-electric');
    var telHeat = $('calc-tel-heating');
    var telWater = $('calc-tel-water');
    if (telEl) {
      telEl.textContent = state.systems.electric
        ? 'Щит ' + calc.shieldModules + ' мод. · ' + calc.elPoints + ' точек'
        : 'Слой отключен';
    }
    if (telHeat) {
      if (!state.systems.heating) {
        telHeat.textContent = 'Слой отключен';
      } else {
        var heatParts = [];
        if (calc.underfloorArea > 0) heatParts.push(calc.heatLoops + ' конт. ТП');
        if (calc.radiators > 0) {
          heatParts.push(calc.radiators + ' ' + plural(calc.radiators, ['радиатор', 'радиатора', 'радиаторов']));
        }
        telHeat.textContent = heatParts.length ? heatParts.join(' · ') : '—';
      }
    }
    if (telWater) {
      telWater.textContent = state.systems.water
        ? state.baths + ' с/у + кухня'
        : 'Слой отключен';
    }

    // HUD над 3D
    var hudDim = $('calc-hud-dim');
    if (hudDim) {
      hudDim.textContent = formatDim(calc.width) + ' × ' + formatDim(calc.length) + ' м · H ' +
        formatMeters(calc.height) + ' · ' + floorLabel() + ' · ' + WALL_LABELS[state.wall];
    }

    var activeNames = [];
    if (state.systems.electric) activeNames.push('Электрика');
    if (state.systems.heating) activeNames.push('Отопление');
    if (state.systems.water) activeNames.push('Вода');
    var hudNets = $('calc-hud-nets');
    if (hudNets) {
      hudNets.textContent = activeNames.length
        ? 'Слои: ' + activeNames.join(' · ')
        : 'Все инженерные слои скрыты';
    }

    // Смета
    var specPanel = $('calc-spec');
    var badge = $('calc-spec-badge');
    if (specPanel) specPanel.classList.toggle('is-locked', !state.unlocked);
    if (badge) {
      badge.textContent = state.unlocked ? 'Открыто' : 'Закрыто';
      badge.classList.toggle('is-locked', !state.unlocked);
      badge.classList.toggle('is-unlocked', state.unlocked);
    }

    setText('calc-spec-el', state.systems.electric ? formatRub(calc.elSubtotal) : 'Откл.');
    setText('calc-cable25', state.systems.electric ? calc.cable25 + ' м' : '—');
    setText('calc-cable15', state.systems.electric ? calc.cable15 + ' м' : '—');
    setText('calc-shield', state.systems.electric ? calc.shieldModules + ' мод.' : '—');
    setText('calc-points', state.systems.electric ? calc.elPoints + ' шт.' : '—');
    setText('calc-points-breakdown', state.systems.electric
      ? calc.sockets + ' / ' + calc.lights + ' / ' + calc.switches
      : '—');

    setText('calc-spec-heat', state.systems.heating ? formatRub(calc.heatSubtotal) : 'Откл.');
    setText('calc-floorpipe', state.systems.heating && calc.underfloorArea > 0 ? calc.floorPipe + ' м' : '—');
    setText('calc-loops', state.systems.heating && calc.heatLoops > 0 ? calc.heatLoops + ' конт.' : '—');
    setText('calc-radiators', state.systems.heating && calc.radiators > 0 ? calc.radiators + ' шт.' : '—');
    setText('calc-radpipe', state.systems.heating && calc.radPipe > 0 ? calc.radPipe + ' м' : '—');

    var radiatorRows = ['calc-radiators-row', 'calc-radpipe-row'];
    radiatorRows.forEach(function (id) {
      var row = $(id);
      if (row) row.hidden = !(state.systems.heating && calc.radiators > 0);
    });

    var underfloorRows = ['calc-floorpipe-row', 'calc-loops-row'];
    underfloorRows.forEach(function (id) {
      var row = $(id);
      if (row) row.hidden = !(state.systems.heating && calc.underfloorArea > 0);
    });

    var boilerRow = $('calc-boiler-row');
    var boilerVisible = state.systems.heating && state.boiler !== 'none';
    if (boilerRow) boilerRow.hidden = !boilerVisible;
    if (boilerVisible) {
      var boilerKind = state.boiler === 'gas' ? 'газовый' : (state.boiler === 'wood' ? 'дровяной' : 'электрический');
      setText('calc-boiler-name', 'Котёл (' + boilerKind + ')');
      setText('calc-boiler-cost', formatRub(calc.boilerMat + calc.boilerWork));
    }

    setText('calc-spec-water', state.systems.water ? formatRub(calc.waterSubtotal) : 'Откл.');
    setText('calc-waterpipe', state.systems.water ? calc.waterPipe + ' м' : '—');
    setText('calc-sewerpipe', state.systems.water ? calc.sewerPipe + ' м' : '—');

    setText('calc-materials', formatRub(calc.materialsTotal));
    setText('calc-work-label', isProject ? 'Монтаж (при заказе)' : 'Монтажные работы');
    setText('calc-work', formatRub(calc.laborTotal));
    setText('calc-project', formatRub(calc.projectCost));
    setText('calc-project-scope', isProject ? 'Только проект (вся РФ)' : 'Включен в смету');
    setText('calc-code', buildProjectCode());

    // Если открыт предпросмотр сообщения — обновить текст
    if (lastMessenger) {
      var msgEl = $('calc-msg-text');
      if (msgEl) msgEl.value = buildMessage();
    }

    scheduleRebuild3D();
    persistParams();
  }

  function setText(id, value) {
    var el = $(id);
    if (el) el.textContent = value;
  }

  /* ------------------------------------------------------------
     Сохранение параметров
     ------------------------------------------------------------ */
  function persistParams() {
    if (!calcParamsLoaded) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        format: state.format,
        width: state.width,
        length: state.length,
        height: state.height,
        floors: state.floors,
        heating1: state.heating1,
        heating2: state.heating2,
        boiler: state.boiler,
        wall: state.wall,
        baths: state.baths,
        systems: state.systems,
        xray: state.xray
      }));
    } catch (e) { /* приватный режим */ }
  }

  function restoreParams() {
    var saved = null;
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (raw) saved = JSON.parse(raw);
    } catch (e) { saved = null; }

    if (saved && typeof saved === 'object') {
      if (saved.format === 'project' || saved.format === 'turnkey') state.format = saved.format;
      if (Number.isFinite(Number(saved.width))) state.width = snap(saved.width, WIDTH_MIN, WIDTH_MAX, WIDTH_STEP);
      if (Number.isFinite(Number(saved.length))) state.length = snap(saved.length, LENGTH_MIN, LENGTH_MAX, LENGTH_STEP);
      if (Number.isFinite(Number(saved.height))) state.height = snap(saved.height, HEIGHT_MIN, HEIGHT_MAX, HEIGHT_STEP);
      if (saved.floors === 1 || saved.floors === 2) state.floors = saved.floors;
      if (saved.heating1 === 'floor' || saved.heating1 === 'radiators') state.heating1 = saved.heating1;
      if (saved.heating2 === 'floor' || saved.heating2 === 'radiators') state.heating2 = saved.heating2;
      if (saved.boiler === 'gas' || saved.boiler === 'electric' || saved.boiler === 'wood' || saved.boiler === 'none') state.boiler = saved.boiler;
      if (saved.wall === 'frame' || saved.wall === 'block' || saved.wall === 'brick') state.wall = saved.wall;
      if ([1, 2, 3].indexOf(saved.baths) !== -1) state.baths = saved.baths;
      if (saved.systems && typeof saved.systems === 'object') {
        state.systems.electric = Boolean(saved.systems.electric);
        state.systems.heating = Boolean(saved.systems.heating);
        state.systems.water = Boolean(saved.systems.water);
      }
      if (typeof saved.xray === 'boolean') state.xray = saved.xray;
    }
    calcParamsLoaded = true;
  }

  /* ------------------------------------------------------------
     Обработчики параметров
     ------------------------------------------------------------ */
  function setDimension(key, value) {
    if (key === 'width') state.width = snap(value, WIDTH_MIN, WIDTH_MAX, WIDTH_STEP);
    if (key === 'length') state.length = snap(value, LENGTH_MIN, LENGTH_MAX, LENGTH_STEP);
    if (key === 'height') state.height = snap(value, HEIGHT_MIN, HEIGHT_MAX, HEIGHT_STEP);
    updateUI();
  }

  function setFormat(value) {
    state.format = value === 'project' ? 'project' : 'turnkey';
    updateUI();
  }

  function setFloors(value) {
    state.floors = value === '2' ? 2 : 1;
    updateUI();
  }

  function setWall(value) {
    if (value === 'frame' || value === 'block' || value === 'brick') {
      state.wall = value;
      updateUI();
    }
  }

  function setBaths(value) {
    var n = parseInt(value, 10);
    if ([1, 2, 3].indexOf(n) !== -1) {
      state.baths = n;
      updateUI();
    }
  }

  function setHeating(floor, type) {
    var value = type === 'radiators' ? 'radiators' : 'floor';
    if (floor === '1') state.heating1 = value;
    if (floor === '2') state.heating2 = value;
    updateUI();
  }

  function setBoiler(type) {
    if (type === 'gas' || type === 'electric' || type === 'wood' || type === 'none') {
      state.boiler = type;
      updateUI();
    }
  }

  function toggleSystem(key) {
    if (Object.prototype.hasOwnProperty.call(state.systems, key)) {
      state.systems[key] = !state.systems[key];
      updateUI();
    }
  }

  function applyPreset(name) {
    var p = PRESETS[name];
    if (!p) return;
    state.width = p.width;
    state.length = p.length;
    state.height = p.height;
    state.floors = p.floors;
    state.wall = p.wall;
    state.baths = p.baths;
    updateUI();
  }

  /* ------------------------------------------------------------
     Делегирование кликов
     ------------------------------------------------------------ */
  section.addEventListener('click', function (e) {
    var el = e.target.closest('[data-calc-format], [data-calc-preset], [data-calc-floors], ' +
      '[data-calc-wall], [data-calc-bath], [data-calc-heating], [data-calc-boiler], ' +
      '[data-calc-system], [data-calc-xray], ' +
      '[data-calc-view], [data-calc-zoom], [data-calc-autorotate], [data-calc-open-form], ' +
      '[data-calc-lock], [data-calc-download], [data-calc-messenger], [data-calc-copy-msg], ' +
      '[data-calc-copy-code], [data-calc-download-project]');
    if (!el) return;

    if (el.hasAttribute('data-calc-format')) { setFormat(el.getAttribute('data-calc-format')); return; }
    if (el.hasAttribute('data-calc-preset')) { applyPreset(el.getAttribute('data-calc-preset')); return; }
    if (el.hasAttribute('data-calc-floors')) { setFloors(el.getAttribute('data-calc-floors')); return; }
    if (el.hasAttribute('data-calc-wall')) { setWall(el.getAttribute('data-calc-wall')); return; }
    if (el.hasAttribute('data-calc-bath')) { setBaths(el.getAttribute('data-calc-bath')); return; }
    if (el.hasAttribute('data-calc-heating')) {
      var parts = el.getAttribute('data-calc-heating').split(':');
      setHeating(parts[0], parts[1]);
      return;
    }
    if (el.hasAttribute('data-calc-boiler')) { setBoiler(el.getAttribute('data-calc-boiler')); return; }
    if (el.hasAttribute('data-calc-system')) { toggleSystem(el.getAttribute('data-calc-system')); return; }

    if (el.hasAttribute('data-calc-xray')) {
      state.xray = !state.xray;
      updateUI();
      return;
    }
    if (el.hasAttribute('data-calc-autorotate')) {
      state.autoRotate = !state.autoRotate;
      updateUI();
      return;
    }
    if (el.hasAttribute('data-calc-view')) { setCameraView(el.getAttribute('data-calc-view')); return; }
    if (el.hasAttribute('data-calc-zoom')) { zoomCamera(num(el.getAttribute('data-calc-zoom'))); return; }
    if (el.hasAttribute('data-calc-open-form')) { openLeadForm(); return; }
    if (el.hasAttribute('data-calc-lock')) { lockSpec(); return; }
    if (el.hasAttribute('data-calc-download')) { downloadSpec(); return; }
    if (el.hasAttribute('data-calc-copy-msg')) { copyMessageAgain(); return; }
    if (el.hasAttribute('data-calc-copy-code')) { copyProjectCode(); return; }
    if (el.hasAttribute('data-calc-download-project')) { downloadDomovoyProject(); return; }
    if (el.hasAttribute('data-calc-messenger')) {
      openMessenger(el.getAttribute('data-calc-messenger'));
    }
  });

  [
    { key: 'width', slider: 'calc-width', number: 'calc-width-num' },
    { key: 'length', slider: 'calc-length', number: 'calc-length-num' },
    { key: 'height', slider: 'calc-height', number: 'calc-height-num' }
  ].forEach(function (cfg) {
    var slider = $(cfg.slider);
    if (slider) {
      slider.addEventListener('input', function () { setDimension(cfg.key, this.value); });
    }
    var number = $(cfg.number);
    if (number) {
      number.addEventListener('change', function () { setDimension(cfg.key, this.value); });
      number.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); this.blur(); }
      });
    }
  });

  /* ------------------------------------------------------------
     Замок сметы и заявка
     ------------------------------------------------------------ */
  function openLeadForm() {
    ensureTurnstile();

    var nameInput = $('calc-name');
    if (nameInput) {
      setTimeout(function () { nameInput.focus(); }, 60);
    }
    var spec = $('calc-spec');
    if (spec) spec.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function lockSpec() {
    state.unlocked = false;
    updateUI();
  }

  var turnstileWidgetId = null;
  var turnstileRetries = 0;

  function ensureTurnstile() {
    var container = $('calc-turnstile');
    if (!container || turnstileWidgetId !== null) return;

    if (!window.turnstile || typeof window.turnstile.render !== 'function') {
      if (turnstileRetries < 25) {
        turnstileRetries += 1;
        setTimeout(ensureTurnstile, 400);
      } else {
        container.innerHTML = '<p class="calc-form-note" style="color:var(--calc-err)">Не удалось загрузить проверку. Обновите страницу или позвоните: ' + PHONE_DISPLAY + '</p>';
      }
      return;
    }

    try {
      turnstileWidgetId = window.turnstile.render(container, {
        sitekey: TURNSTILE_SITEKEY,
        theme: 'dark',
        size: 'flexible',
        language: 'ru'
      });
    } catch (e) {
      container.innerHTML = '<p class="calc-form-note" style="color:var(--calc-err)">Проверка недоступна. Позвоните: ' + PHONE_DISPLAY + '</p>';
    }
  }

  function submitLead(e) {
    e.preventDefault();

    var form = $('calc-lead-form');
    if (!form) return;

    var nameEl = $('calc-name');
    var contactEl = $('calc-contact');
    var channelEl = $('calc-channel');
    var websiteEl = $('calc-website');
    var errEl = $('calc-form-error');
    var submitBtn = $('calc-lead-submit');

    var name = nameEl ? nameEl.value.trim() : '';
    var contact = contactEl ? contactEl.value.trim() : '';
    var channel = channelEl ? channelEl.value : 'Telegram';
    var website = websiteEl ? websiteEl.value.trim() : '';

    function showError(msg, ok) {
      if (!errEl) return;
      errEl.textContent = msg;
      errEl.classList.toggle('is-ok', !!ok);
    }

    if (name.length < 2) {
      showError('Укажите имя — минимум 2 символа.');
      if (nameEl) nameEl.focus();
      return;
    }
    if (contact.length < 4) {
      showError('Укажите телефон, ник в TG/MAX или e-mail.');
      if (contactEl) contactEl.focus();
      return;
    }

    var tokenInput = form.querySelector('[name="cf-turnstile-response"]');
    var token = tokenInput ? tokenInput.value : '';
    if (!token) {
      showError('Подтвердите, что вы не робот, и попробуйте ещё раз.');
      return;
    }

    var calc = calculate();
    var summary = [
      state.format === 'project' ? '3D-проект' : 'Проект + монтаж',
      formatDim(calc.width) + '×' + formatDim(calc.length) + ' м',
      calc.area + ' м²',
      state.floors === 2 ? '2 эт.' : '1 эт.',
      WALL_LABELS[state.wall],
      state.baths + ' с/у',
      Math.round(calc.rangeMin / 1000) + '–' + Math.round(calc.rangeMax / 1000) + ' тыс. ₽'
    ].join(' | ').slice(0, 100);

    var payload = {
      name: name,
      phone: contact,
      objectType: summary,
      message: buildSpecText() + '\nКанал связи: ' + channel,
      website: website,
      turnstileToken: token
    };

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.dataset.originalText = submitBtn.textContent;
      submitBtn.textContent = 'Отправляем заявку…';
    }
    showError('');

    fetch(LEAD_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(function (res) {
        return res.json().then(function (data) { return { res: res, data: data }; });
      })
      .then(function (r) {
        if (!r.data || !r.data.ok) {
          var rejected = new Error('lead_rejected');
          rejected.code = 'rejected';
          throw rejected;
        }
        unlockSpecFor(name, contact, channel);
        reachGoal('lead_form_submit');
      })
      .catch(function (err) {
        if (err && err.code === 'rejected') {
          showError('Не удалось отправить заявку. Попробуйте ещё раз или позвоните: ' + PHONE_DISPLAY);
          return;
        }
        // Сервер заявок недоступен (VPS/сеть/Cloudflare): не оставляем
        // посетителя с закрытой сметой — открываем её и предлагаем мессенджеры.
        unlockSpecFor(name, contact, channel);
        showError('Сервер заявок временно недоступен. Спецификация открыта — напишите в TG или MAX, чтобы получить точную ведомость.', true);
      })
      .finally(function () {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = submitBtn.dataset.originalText || 'Получить спецификацию';
        }
      });
  }

  function unlockSpecFor(name, contact, channel) {
    state.unlocked = true;
    state.lead = { name: name, contact: contact, channel: channel };

    var note = $('calc-unlocked-note');
    if (note) note.textContent = 'Спецификация открыта для ' + name + ' (' + channel + ')';

    if (turnstileWidgetId !== null && window.turnstile) {
      try { window.turnstile.reset(turnstileWidgetId); } catch (err) {}
    }
    updateUI();

    var spec = $('calc-spec');
    if (spec) spec.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  var leadForm = $('calc-lead-form');
  if (leadForm) leadForm.addEventListener('submit', submitLead);

  /* ------------------------------------------------------------
     Текст спецификации и скачивание
     ------------------------------------------------------------ */
  function buildSpecText() {
    var calc = lastCalc || calculate();
    var lines = [
      'СПЕЦИФИКАЦИЯ ИНЖЕНЕРНЫХ СЕТЕЙ «ДОМОВОЙ»',
      '--------------------------------------------------',
      'Формат заказа: ' + formatLabel(),
      'Габариты дома: ' + formatDim(calc.width) + ' × ' + formatDim(calc.length) + ' м, высота этажа ' + formatMeters(calc.height),
      'Площадь дома: ' + calc.area + ' м²',
      'Периметр: ' + calc.perimeter + ' м',
      'Этажность: ' + floorLabel(),
      'Отопление 1 этажа: ' + (state.heating1 === 'floor' ? 'тёплый пол' : 'радиаторы'),
      (state.floors === 2 ? 'Отопление 2 этажа: ' + (state.heating2 === 'floor' ? 'тёплый пол' : 'радиаторы') : ''),
      'Котёл: ' + boilerLabel(),
      'Материал стен: ' + WALL_LABELS[state.wall],
      'Санузлы: ' + state.baths,
      'Код проекта: ' + buildProjectCode(),
      'Ориентир стоимости: от ' + formatRub(calc.rangeMin) + ' до ' + formatRub(calc.rangeMax),
      '',
      'ОБЪЕМЫ ПО УЗЛАМ:',
      '- Электрика: ' + (state.systems.electric
        ? 'ВВГнг-LS 3x2.5 — ' + calc.cable25 + ' м; 3x1.5 — ' + calc.cable15 + ' м; щит — ' + calc.shieldModules + ' мод.; точек — ' + calc.elPoints + ' шт. (розетки/свет/выключатели: ' + calc.sockets + '/' + calc.lights + '/' + calc.switches + ')'
        : 'не включена'),
      '- Отопление: ' + (state.systems.heating
        ? [
            calc.underfloorArea > 0 ? 'тёплый пол PEX-a — ' + calc.floorPipe + ' м, ' + calc.heatLoops + ' конт.' : '',
            calc.radiators > 0 ? 'радиаторы — ' + calc.radiators + ' шт., подводка — ' + calc.radPipe + ' м' : '',
            calc.boilerPowerKw > 0 ? 'котёл — ' + boilerLabel() : ''
          ].filter(Boolean).join('; ')
        : 'не включено'),
      '- Водоснабжение / канализация: ' + (state.systems.water
        ? 'ХВС/ГВС — ' + calc.waterPipe + ' м; канализация — ' + calc.sewerPipe + ' м'
        : 'не включено'),
      '',
      'РАЗБИВКА СТОИМОСТИ:',
      '- Материалы (ориентир): ' + formatRub(calc.materialsTotal),
      '- Монтажные работы: ' + formatRub(calc.laborTotal),
      '- 3D-проект «Домовой»: ' + formatRub(calc.projectCost),
      '',
      'Контакт: ' + PHONE_DISPLAY + ' (TG / MAX)',
      '* Расчет предварительный, не является публичной офертой.'
    ];
    return lines.join('\n');
  }

  function downloadSpec() {
    var text = buildSpecText();
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'domovoy-spec-' + formatDim(state.width) + 'x' + formatDim(state.length) + 'm.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1500);
  }

  /* ------------------------------------------------------------
     Код проекта и выгрузка в программу «Домовой»
     ------------------------------------------------------------ */
  function buildProjectCode() {
    var w = clamp(Math.round((state.width - WIDTH_MIN) / WIDTH_STEP), 0, 20);
    var l = clamp(Math.round((state.length - LENGTH_MIN) / LENGTH_STEP), 0, 28);
    var h = clamp(Math.round((state.height - HEIGHT_MIN) / HEIGHT_STEP), 0, 8);
    var floors = state.floors === 2 ? 1 : 0;
    var wall = state.wall === 'frame' ? 0 : (state.wall === 'block' ? 1 : 2);
    var baths = state.baths - 1;
    var systems = (state.systems.electric ? 1 : 0) |
                  (state.systems.heating ? 2 : 0) |
                  (state.systems.water ? 4 : 0);
    var heating1 = state.heating1 === 'radiators' ? 1 : 0;
    var heating2 = state.heating2 === 'radiators' ? 1 : 0;
    var boiler = state.boiler === 'gas' ? 0 : (state.boiler === 'electric' ? 1 : (state.boiler === 'wood' ? 2 : 3));

    var payload = w | (l << 5) | (h << 10) | (floors << 14) |
                  (wall << 16) | (baths << 18) | (systems << 20) |
                  (heating1 << 23) | (heating2 << 24) | (boiler << 25);
    var body = payload.toString(36).toUpperCase();
    while (body.length < 6) body = '0' + body;

    var sum = 0;
    for (var i = 0; i < body.length; i++) sum += parseInt(body[i], 36);
    var checksum = (sum % 36).toString(36).toUpperCase();
    return 'DOM-' + body + '-' + checksum;
  }

  function copyProjectCode() {
    var code = buildProjectCode();
    var btn = section.querySelector('[data-calc-copy-code]');
    var original = btn ? btn.textContent : '';
    copyText(code, function (ok) {
      if (!btn) return;
      btn.textContent = ok ? 'Код скопирован' : 'Скопируйте вручную';
      setTimeout(function () { btn.textContent = original; }, 1600);
    });
  }

  function buildDomovoyProject() {
    var calc = lastCalc || calculate();
    var W = Math.round(state.width * 1000);
    var D = Math.round(state.length * 1000);
    var H = Math.round(state.height * 1000);
    var thickness = state.wall === 'frame' ? 200 : (state.wall === 'block' ? 300 : 380);
    var material = state.wall === 'frame' ? 'каркас/СИП' : (state.wall === 'block' ? 'газобетон' : 'кирпич');
    var floorCount = state.floors;
    var floors = [];

    for (var f = 0; f < floorCount; f++) {
      var floorName = f === 0 ? '1 этаж' : '2 этаж';
      var floorId = 'floor-' + (f + 1);
      var prefix = 'f' + (f + 1) + '-';

      var walls = [
        { id: prefix + 'w-north', name: 'Наружная стена · север', start: { x: 0, y: 0 }, end: { x: W, y: 0 }, thickness: thickness, material: material },
        { id: prefix + 'w-east', name: 'Наружная стена · восток', start: { x: W, y: 0 }, end: { x: W, y: D }, thickness: thickness, material: material },
        { id: prefix + 'w-south', name: 'Наружная стена · юг', start: { x: W, y: D }, end: { x: 0, y: D }, thickness: thickness, material: material },
        { id: prefix + 'w-west', name: 'Наружная стена · запад', start: { x: 0, y: D }, end: { x: 0, y: 0 }, thickness: thickness, material: material }
      ];

      floors.push({
        id: floorId,
        name: floorName,
        elevation: f * H,
        ceilingHeightMm: H,
        cableRoutingStyle: 'ceiling-trunk',
        walls: walls,
        openings: [],
        dimensions: [],
        rooms: [],
        points: buildProjectPoints(prefix, W, D, H),
        cableRoutes: [],
        panel: {
          id: 'panel-' + (f + 1),
          x: 500,
          y: 500,
          name: f === 0 ? 'ЩР-1 · вводной щит' : 'ЩР-2 · этажный щит',
          placed: true,
          phaseCount: 1,
          nominalVoltage: 230,
          installationHeight: 1500,
          incomerKind: 'aerial-sip'
        }
      });
    }

    return {
      schemaVersion: 1,
      id: 'web-' + Date.now(),
      name: 'Дом ' + formatDim(state.width) + '×' + formatDim(state.length) + ' · ' + WALL_LABELS[state.wall],
      address: '',
      units: 'mm',
      updatedAt: new Date().toISOString(),
      floors: floors,
      circuits: [
        { id: 'c-light', name: 'Освещение', breaker: 'B10', color: '#d88b37', load: 1.18, purpose: 'lighting' },
        { id: 'c-sockets', name: 'Розеточная группа', breaker: 'B16', color: '#2b8ca1', load: 2.46, purpose: 'sockets' },
        { id: 'c-kitchen', name: 'Кухня · техника', breaker: 'B20', color: '#3a6fb0', load: 3.2, purpose: 'sockets' },
        { id: 'c-spare', name: 'Резерв', breaker: 'B16', color: '#8b9aa3', load: 0, purpose: 'other' }
      ],
      normativeProfile: {
        phaseCount: 1,
        nominalVoltage: 230,
        allocatedPowerKw: calc.area > 180 ? 25 : (calc.area > 120 ? 20 : 15),
        conductorMaterial: 'copper',
        installationMethod: 'Скрытая прокладка',
        reservePercent: 10,
        ruleSetName: 'Не выбран'
      },
      webCalculator: {
        source: 'https://electric.vim-scrum.ru/#calculator-section',
        code: buildProjectCode(),
        widthM: state.width,
        lengthM: state.length,
        heightM: state.height,
        areaM2: calc.area,
        perimeterM: calc.perimeter,
        floors: state.floors,
        wallType: state.wall,
        baths: state.baths,
        heating1: state.heating1,
        heating2: state.floors === 2 ? state.heating2 : null,
        boiler: state.boiler,
        boilerPowerKw: calc.boilerPowerKw,
        underfloorAreaM2: calc.underfloorArea,
        radiators: calc.radiators,
        points: {
          total: calc.elPoints,
          sockets: calc.sockets,
          lights: calc.lights,
          switches: calc.switches,
          outputs: calc.outputs
        },
        systems: {
          electric: state.systems.electric,
          heating: state.systems.heating,
          water: state.systems.water
        },
        estimateMin: calc.rangeMin,
        estimateMax: calc.rangeMax,
        generatedAt: new Date().toISOString()
      }
    };
  }

  function buildProjectPoints(prefix, W, D, H) {
    var points = [];
    var pad = 350;
    var socketCoords = [
      [pad, Math.round(D * 0.3)],
      [pad, Math.round(D * 0.7)],
      [W - pad, Math.round(D * 0.3)],
      [W - pad, Math.round(D * 0.7)],
      [Math.round(W * 0.3), pad],
      [Math.round(W * 0.7), pad]
    ];
    socketCoords.forEach(function (c, i) {
      points.push({
        id: prefix + 'socket-' + (i + 1),
        kind: 'socket',
        x: c[0],
        y: c[1],
        name: 'Розетка ' + (i + 1),
        circuitId: 'c-sockets',
        installationHeight: 300,
        mounting: 'wall'
      });
    });

    var lightCoords = [
      [Math.round(W * 0.25), Math.round(D * 0.3)],
      [Math.round(W * 0.75), Math.round(D * 0.3)],
      [Math.round(W * 0.25), Math.round(D * 0.7)],
      [Math.round(W * 0.75), Math.round(D * 0.7)]
    ];
    lightCoords.forEach(function (c, i) {
      points.push({
        id: prefix + 'light-' + (i + 1),
        kind: 'light',
        x: c[0],
        y: c[1],
        name: 'Свет ' + (i + 1),
        circuitId: 'c-light',
        installationHeight: Math.max(2400, H - 100),
        mounting: 'ceiling'
      });
    });

    [
      [650, D - 650],
      [W - 650, D - 650]
    ].forEach(function (c, i) {
      points.push({
        id: prefix + 'switch-' + (i + 1),
        kind: 'switch',
        x: c[0],
        y: c[1],
        name: 'Выключатель ' + (i + 1),
        circuitId: 'c-light',
        installationHeight: 900,
        mounting: 'wall'
      });
    });

    return points;
  }

  function downloadDomovoyProject() {
    var project = buildDomovoyProject();
    var content = JSON.stringify(project, null, 2);
    var blob = new Blob([content], { type: 'application/json;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'domovoy-' + formatDim(state.width) + 'x' + formatDim(state.length) + '-' + (state.floors === 2 ? '2fl' : '1fl') + '.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1500);
    reachGoal('project_export');
  }

  /* ------------------------------------------------------------
     Мессенджеры: deep-link + копирование текста
     ------------------------------------------------------------ */
  var lastMessenger = null;

  function buildMessage() {
    var calc = lastCalc || calculate();
    var systems = [];
    if (state.systems.electric) systems.push('электрика и щит');
    if (state.systems.heating) {
      var heatingParts = ['1 эт. — ' + (state.heating1 === 'floor' ? 'ТП' : 'радиаторы')];
      if (state.floors === 2) heatingParts.push('2 эт. — ' + (state.heating2 === 'floor' ? 'ТП' : 'радиаторы'));
      if (calc.boilerPowerKw > 0) {
        heatingParts.push('котёл ' + boilerLabel());
      }
      systems.push('отопление (' + heatingParts.join(', ') + ')');
    }
    if (state.systems.water) systems.push('водоснабжение и септик');

    var telegram = 'Здравствуйте! Рассчитал ' + WALL_HOUSE[state.wall] + ': ' +
      formatDim(calc.width) + '×' + formatDim(calc.length) + ' м, ' +
      floorLabel() + ', высота этажа ' + formatMeters(calc.height) + ', ' +
      (systems.length ? systems.join(', ') : 'инженерные сети по согласованию') + '. ' +
      'Отправьте, пожалуйста, спецификацию материалов и схему из программы «Домовой». ' +
      'Предварительный ориентир: от ' + formatRub(calc.rangeMin) + ' до ' + formatRub(calc.rangeMax) + '. ' +
      'Код проекта: ' + buildProjectCode() + '.';

    if (state.lead.name) {
      telegram += '\nКонтакт: ' + state.lead.name + ' (' + state.lead.contact + ')';
    }
    return telegram;
  }

  function showMessage(text, channel) {
    lastMessenger = channel;
    var box = $('calc-msg-box');
    var title = $('calc-msg-title');
    var ta = $('calc-msg-text');
    var status = $('calc-msg-status');

    if (box) box.classList.add('is-visible');
    if (title) title.textContent = 'Текст заявки для ' + channel;
    if (ta) ta.value = text;
    if (status) status.textContent = '';

    copyText(text, function (ok) {
      if (!status) return;
      if (ok) {
        status.textContent = channel === 'MAX'
          ? 'Текст скопирован — вставьте в чат MAX'
          : 'Текст скопирован — можно отправить в TG';
      } else {
        status.textContent = 'Скопируйте текст вручную из поля ниже';
      }
    });
  }

  function openMessenger(channel) {
    var msg = buildMessage();
    reachGoal('messenger_click');
    showMessage(msg, channel === 'max' ? 'MAX' : 'TG');

    var url = channel === 'max'
      ? MAX_URL
      : TG_URL + '?text=' + encodeURIComponent(msg);

    var win = null;
    try { win = window.open(url, '_blank', 'noopener'); } catch (e) { win = null; }

    if (!win) {
      var status = $('calc-msg-status');
      if (status) status.textContent = 'Разрешите всплывающие окна или скопируйте текст вручную';
    }
  }

  function copyMessageAgain() {
    var ta = $('calc-msg-text');
    var status = $('calc-msg-status');
    if (!ta) return;
    copyText(ta.value, function (ok) {
      if (status) status.textContent = ok ? 'Текст скопирован в буфер обмена' : 'Скопируйте вручную';
    });
  }

  function copyText(text, done) {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      navigator.clipboard.writeText(text).then(function () {
        done(true);
      }).catch(function () {
        done(fallbackCopy(text));
      });
    } else {
      done(fallbackCopy(text));
    }
  }

  function fallbackCopy(text) {
    try {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      var ok = document.execCommand('copy');
      document.body.removeChild(ta);
      return ok;
    } catch (e) {
      return false;
    }
  }

  /* ------------------------------------------------------------
     Three.js: ленивая загрузка и сцена
     ------------------------------------------------------------ */
  var THREE = null;
  var scene = null;
  var camera = null;
  var renderer = null;
  var houseGroup = null;
  var gridHelper = null;
  var sceneReady = false;
  var sceneVisible = false;
  var rafId = null;
  var threeLoading = false;
  var threeFailed = false;
  var stageResizeObserver = null;

  var camTarget = null;
  var spherical = { theta: Math.PI / 4, phi: Math.PI / 3.1, radius: 20 };
  var targetSpherical = { theta: Math.PI / 4, phi: Math.PI / 3.1, radius: 20 };
  var homeRadius = 20;
  var firstBuild = true;

  var pointers = new Map();
  var prevPointer = { x: 0, y: 0 };
  var pinchStart = 0;

  var isCoarse = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
  var reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function loadThree() {
    if (window.THREE) {
      THREE = window.THREE;
      initThree();
      return;
    }
    if (threeLoading || threeFailed) return;
    threeLoading = true;

    var script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js';
    script.async = true;
    script.onload = function () {
      threeLoading = false;
      if (window.THREE) {
        THREE = window.THREE;
        initThree();
      } else {
        failThree();
      }
    };
    script.onerror = function () {
      threeLoading = false;
      failThree();
    };
    document.head.appendChild(script);
  }

  function failThree() {
    threeFailed = true;
    var loading = $('calc-stage-loading');
    var fallback = $('calc-stage-fallback');
    if (loading) loading.classList.add('is-hidden');
    if (fallback) fallback.classList.add('is-visible');
  }

  function initThree() {
    var stage = $('calc-stage');
    var canvas = $('calc-canvas');
    if (!stage || !canvas || !THREE) return;

    var width = stage.clientWidth;
    var height = stage.clientHeight;
    if (!width || !height) {
      setTimeout(initThree, 200);
      return;
    }

    scene = new THREE.Scene();
    camTarget = new THREE.Vector3(0, 1.4, 0);

    camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 220);

    try {
      renderer = new THREE.WebGLRenderer({
        canvas: canvas,
        antialias: true,
        alpha: true,
        powerPreference: 'high-performance'
      });
    } catch (e) {
      failThree();
      return;
    }

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, isCoarse ? 1.75 : 2));
    renderer.setSize(width, height, false);
    renderer.setClearColor(0x000000, 0);

    var ambient = new THREE.AmbientLight(0xdbeafe, 0.8);
    scene.add(ambient);

    var dirLight = new THREE.DirectionalLight(0xffffff, 1.0);
    dirLight.position.set(12, 18, 10);
    scene.add(dirLight);

    var rimLight = new THREE.DirectionalLight(0x7dd3fc, 0.35);
    rimLight.position.set(-10, 8, -12);
    scene.add(rimLight);

    gridHelper = new THREE.GridHelper(30, 30, 0x33415c, 0x1e293b);
    gridHelper.position.y = -0.02;
    if (gridHelper.material) {
      gridHelper.material.transparent = true;
      gridHelper.material.opacity = 0.55;
    }
    scene.add(gridHelper);

    houseGroup = new THREE.Group();
    scene.add(houseGroup);

    setupControls(canvas, stage);

    sceneReady = true;
    var loading = $('calc-stage-loading');
    if (loading) loading.classList.add('is-hidden');

    rebuildHouse3D();
    if (sceneVisible) startLoop();
  }

  function setupControls(canvas, stage) {
    canvas.addEventListener('pointerdown', function (e) {
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 1) {
        prevPointer = { x: e.clientX, y: e.clientY };
        canvas.setPointerCapture(e.pointerId);
      } else if (pointers.size === 2) {
        pinchStart = pointerDistance();
      }
    });

    canvas.addEventListener('pointermove', function (e) {
      if (!pointers.has(e.pointerId)) return;
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

      if (pointers.size === 2) {
        var dist = pointerDistance();
        if (pinchStart > 0) {
          var delta = (pinchStart - dist) * 0.035;
          if (Math.abs(delta) > 0.02) zoomCamera(delta);
        }
        pinchStart = dist;
        return;
      }

      if (pointers.size === 1) {
        var dx = e.clientX - prevPointer.x;
        var dy = e.clientY - prevPointer.y;
        prevPointer = { x: e.clientX, y: e.clientY };
        targetSpherical.theta -= dx * 0.008;
        targetSpherical.phi = clamp(targetSpherical.phi - dy * 0.008, 0.18, Math.PI / 2 - 0.08);
      }
    });

    function endPointer(e) {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) pinchStart = 0;
      if (pointers.size === 1) {
        var remaining = pointers.values().next().value;
        prevPointer = { x: remaining.x, y: remaining.y };
      }
      try { canvas.releasePointerCapture(e.pointerId); } catch (err) {}
    }
    canvas.addEventListener('pointerup', endPointer);
    canvas.addEventListener('pointercancel', endPointer);
    canvas.addEventListener('lostpointercapture', function (e) {
      pointers.delete(e.pointerId);
    });

    canvas.addEventListener('wheel', function (e) {
      e.preventDefault();
      zoomCamera(e.deltaY > 0 ? 1.6 : -1.6);
    }, { passive: false });

    if (typeof ResizeObserver !== 'undefined') {
      stageResizeObserver = new ResizeObserver(function () {
        if (!stage || !camera || !renderer) return;
        var w = stage.clientWidth;
        var h = stage.clientHeight;
        if (w > 0 && h > 0) {
          camera.aspect = w / h;
          camera.updateProjectionMatrix();
          renderer.setSize(w, h, false);
        }
      });
      stageResizeObserver.observe(stage);
    }
  }

  function pointerDistance() {
    var pts = Array.from(pointers.values());
    if (pts.length < 2) return 0;
    var dx = pts[0].x - pts[1].x;
    var dy = pts[0].y - pts[1].y;
    return Math.sqrt(dx * dx + dy * dy);
  }

  function setCameraView(mode) {
    if (mode === 'top') {
      targetSpherical.phi = 0.19;
      targetSpherical.theta = 0;
      targetSpherical.radius = homeRadius * 1.12;
    } else {
      targetSpherical.theta = Math.PI / 4;
      targetSpherical.phi = Math.PI / 3.1;
      targetSpherical.radius = homeRadius;
    }
    section.querySelectorAll('[data-calc-view]').forEach(function (btn) {
      btn.classList.toggle('is-active', btn.getAttribute('data-calc-view') === mode);
    });
  }

  function zoomCamera(delta) {
    targetSpherical.radius = clamp(
      targetSpherical.radius + delta,
      homeRadius * 0.55,
      homeRadius * 1.9
    );
  }

  function startLoop() {
    if (rafId || !sceneReady) return;
    function animate() {
      rafId = requestAnimationFrame(animate);
      if (!sceneReady || !camera || !renderer) return;

      if (state.autoRotate && pointers.size === 0 && !reducedMotion) {
        targetSpherical.theta += 0.0035;
      }

      var ease = 0.12;
      spherical.theta += (targetSpherical.theta - spherical.theta) * ease;
      spherical.phi += (targetSpherical.phi - spherical.phi) * ease;
      spherical.radius += (targetSpherical.radius - spherical.radius) * ease;

      var sinPhi = Math.sin(spherical.phi);
      camera.position.set(
        camTarget.x + spherical.radius * sinPhi * Math.sin(spherical.theta),
        camTarget.y + spherical.radius * Math.cos(spherical.phi),
        camTarget.z + spherical.radius * sinPhi * Math.cos(spherical.theta)
      );
      camera.lookAt(camTarget);
      renderer.render(scene, camera);
    }
    animate();
  }

  function stopLoop() {
    if (rafId) cancelAnimationFrame(rafId);
    rafId = null;
  }

  function disposeGroup(group) {
    if (!group) return;
    while (group.children.length > 0) {
      var obj = group.children[0];
      group.remove(obj);
      if (obj.children && obj.children.length) disposeGroup(obj);
      if (obj.geometry) obj.geometry.dispose();
      if (obj.material) {
        if (Array.isArray(obj.material)) {
          obj.material.forEach(function (m) { if (m && m.dispose) m.dispose(); });
        } else if (obj.material.dispose) {
          obj.material.dispose();
        }
      }
    }
  }

  var rebuildQueued = false;

  function scheduleRebuild3D() {
    if (!sceneReady || rebuildQueued) return;
    rebuildQueued = true;
    requestAnimationFrame(function () {
      rebuildQueued = false;
      rebuildHouse3D();
    });
  }

  function addLine(parent, points, colorHex) {
    var geo = new THREE.BufferGeometry().setFromPoints(
      points.map(function (p) { return new THREE.Vector3(p[0], p[1], p[2]); })
    );
    var mat = new THREE.LineBasicMaterial({ color: colorHex, transparent: true, opacity: 0.8 });
    parent.add(new THREE.Line(geo, mat));
  }

  function addTube(parent, p1, p2, radius, colorHex) {
    var v1 = new THREE.Vector3(p1[0], p1[1], p1[2]);
    var v2 = new THREE.Vector3(p2[0], p2[1], p2[2]);
    var dist = v1.distanceTo(v2);
    if (dist < 0.01) return;
    var geo = new THREE.CylinderGeometry(radius, radius, dist, 6);
    var mat = new THREE.MeshBasicMaterial({ color: colorHex });
    var mesh = new THREE.Mesh(geo, mat);
    mesh.position.copy(v1).add(v2).multiplyScalar(0.5);
    mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), v2.clone().sub(v1).normalize());
    parent.add(mesh);
  }

  function addNode(parent, x, y, z, colorHex, size) {
    var geo = new THREE.SphereGeometry(size || 0.075, 8, 8);
    var mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: colorHex }));
    mesh.position.set(x, y, z);
    parent.add(mesh);
  }

  function rebuildHouse3D() {
    if (!sceneReady || !houseGroup) return;
    disposeGroup(houseGroup);

    var floors = state.floors;
    var W = state.width;
    var D = state.length;
    var floorH = state.height;
    var totalH = floorH * floors;

    homeRadius = Math.max(12, Math.max(W, D) * 1.65, totalH * 2.0);
    if (!camTarget) camTarget = new THREE.Vector3(0, totalH * 0.48, 0);
    camTarget.y = totalH * 0.48;

    if (firstBuild) {
      spherical.radius = homeRadius;
      targetSpherical.radius = homeRadius;
      firstBuild = false;
    } else {
      targetSpherical.radius = clamp(targetSpherical.radius, homeRadius * 0.55, homeRadius * 1.9);
    }

    // Фундамент
    var slabGeo = new THREE.BoxGeometry(W + 0.35, 0.24, D + 0.35);
    var slab = new THREE.Mesh(slabGeo, new THREE.MeshStandardMaterial({
      color: 0x1b2333,
      roughness: 0.85
    }));
    slab.position.y = 0.12;
    houseGroup.add(slab);

    var slabEdges = new THREE.LineSegments(
      new THREE.EdgesGeometry(slabGeo),
      new THREE.LineBasicMaterial({ color: 0x475569 })
    );
    slabEdges.position.copy(slab.position);
    houseGroup.add(slabEdges);

    var wallColor = WALL_3D_COLORS[state.wall] || 0x66788f;
    var wallOpacity = state.xray ? 0.15 : 0.66;

    for (var f = 0; f < floors; f++) {
      var baseY = 0.24 + f * floorH;

      if (f > 0) {
        var midGeo = new THREE.BoxGeometry(W, 0.14, D);
        var mid = new THREE.Mesh(midGeo, new THREE.MeshStandardMaterial({
          color: 0x293245,
          transparent: true,
          opacity: state.xray ? 0.35 : 0.85
        }));
        mid.position.y = baseY;
        houseGroup.add(mid);
      }

      var shellGeo = new THREE.BoxGeometry(W, floorH, D);
      var shell = new THREE.Mesh(shellGeo, new THREE.MeshStandardMaterial({
        color: wallColor,
        transparent: true,
        opacity: wallOpacity,
        depthWrite: !state.xray
      }));
      shell.position.y = baseY + floorH / 2;
      houseGroup.add(shell);

      var shellEdges = new THREE.LineSegments(
        new THREE.EdgesGeometry(shellGeo),
        new THREE.LineBasicMaterial({ color: 0x5c7c9e, transparent: true, opacity: 0.45 })
      );
      shellEdges.position.copy(shell.position);
      houseGroup.add(shellEdges);

      // Внутренние перегородки — визуальное зонирование
      var partMat = new THREE.MeshStandardMaterial({
        color: 0x475569,
        transparent: true,
        opacity: state.xray ? 0.18 : 0.42,
        depthWrite: false
      });
      var part1 = new THREE.Mesh(new THREE.BoxGeometry(0.08, floorH - 0.1, D * 0.96), partMat);
      part1.position.set(-W * 0.12, baseY + floorH / 2, 0);
      houseGroup.add(part1);

      var part2 = new THREE.Mesh(new THREE.BoxGeometry(W * 0.58, floorH - 0.1, 0.08), partMat);
      part2.position.set(W * 0.19, baseY + floorH / 2, 0);
      houseGroup.add(part2);
    }

    // Скатная кровля — инженерный каркас
    var roofBaseY = 0.24 + totalH;
    var ridgeH = 1.6;
    var hw = W / 2 + 0.25;
    var hd = D / 2 + 0.25;
    var roofLines = [
      [[-hw, roofBaseY, -hd], [0, roofBaseY + ridgeH, -hd]],
      [[hw, roofBaseY, -hd], [0, roofBaseY + ridgeH, -hd]],
      [[-hw, roofBaseY, hd], [0, roofBaseY + ridgeH, hd]],
      [[hw, roofBaseY, hd], [0, roofBaseY + ridgeH, hd]],
      [[0, roofBaseY + ridgeH, -hd], [0, roofBaseY + ridgeH, hd]],
      [[-hw, roofBaseY, -hd], [-hw, roofBaseY, hd]],
      [[hw, roofBaseY, -hd], [hw, roofBaseY, hd]],
      [[-hw, roofBaseY, -hd], [hw, roofBaseY, -hd]],
      [[-hw, roofBaseY, hd], [hw, roofBaseY, hd]]
    ];
    roofLines.forEach(function (pair) { addLine(houseGroup, pair, 0x3f4f6b); });

    var techX = -W * 0.36;
    var techZ = -D * 0.32;

    // ============ СЕТЬ 1: ЭЛЕКТРИКА ============
    if (state.systems.electric) {
      var elColor = 0xffd24a;

      var panel = new THREE.Mesh(
        new THREE.BoxGeometry(0.45, 0.65, 0.16),
        new THREE.MeshBasicMaterial({ color: elColor })
      );
      panel.position.set(techX + 0.35, 1.55, -D / 2 + 0.14);
      houseGroup.add(panel);

      for (var ef = 0; ef < floors; ef++) {
        var ceilY = 0.24 + (ef + 1) * floorH - 0.18;
        var sockY = 0.24 + ef * floorH + 0.42;
        var startY = ef === 0 ? 1.55 : 0.24 + ef * floorH + 0.2;
        var startX = techX + 0.35;
        var startZ = -D / 2 + 0.14;

        addTube(houseGroup, [startX, startY, startZ], [startX, ceilY, startZ], 0.032, elColor);
        addTube(houseGroup, [startX, ceilY, startZ], [startX, ceilY, D * 0.35], 0.028, elColor);
        addTube(houseGroup, [-W * 0.38, ceilY, 0], [W * 0.38, ceilY, 0], 0.028, elColor);
        addTube(houseGroup, [W * 0.28, ceilY, -D * 0.35], [W * 0.28, ceilY, D * 0.35], 0.024, elColor);

        var outlets = [
          [-W * 0.38, 0],
          [W * 0.38, 0],
          [W * 0.28, -D * 0.35],
          [W * 0.28, D * 0.35],
          [startX, D * 0.35]
        ];
        outlets.forEach(function (o) {
          addTube(houseGroup, [o[0], ceilY, o[1]], [o[0], sockY, o[1]], 0.02, elColor);
          addNode(houseGroup, o[0], sockY, o[1], elColor, 0.07);
        });

        [[-W * 0.24, -D * 0.18], [W * 0.22, -D * 0.18], [W * 0.22, D * 0.22], [-W * 0.24, D * 0.22]]
          .forEach(function (l) {
            addTube(houseGroup, [l[0], ceilY, 0], [l[0], ceilY, l[1]], 0.016, elColor);
            var lamp = new THREE.Mesh(
              new THREE.OctahedronGeometry(0.1),
              new THREE.MeshBasicMaterial({ color: elColor })
            );
            lamp.position.set(l[0], ceilY - 0.05, l[1]);
            houseGroup.add(lamp);
          });
      }
    }

    // ============ СЕТЬ 2: ОТОПЛЕНИЕ / ТП ============
    if (state.systems.heating) {
      var heatColor = 0xff5a4d;
      var floorHeating = [state.heating1];
      if (floors === 2) floorHeating.push(state.heating2);
      var hasUnderfloor = floorHeating.indexOf('floor') !== -1;

      if (hasUnderfloor) {
        var manifold = new THREE.Mesh(
          new THREE.BoxGeometry(0.55, 0.5, 0.18),
          new THREE.MeshBasicMaterial({ color: heatColor })
        );
        manifold.position.set(techX - 0.2, 0.85, -D / 2 + 0.18);
        houseGroup.add(manifold);
      }

      // Котёл в техническом углу
      if (state.boiler !== 'none') {
        var boilerBox = new THREE.Mesh(
          new THREE.BoxGeometry(0.6, 1.2, 0.4),
          new THREE.MeshBasicMaterial({ color: 0xff9f43 })
        );
        boilerBox.position.set(techX - 0.55, 0.85, techZ);
        houseGroup.add(boilerBox);
        addTube(houseGroup, [techX - 0.55, 1.45, techZ], [techX - 0.55, totalH - 0.2, techZ], 0.03, heatColor);
      }

      for (var hf = 0; hf < floors; hf++) {
        var ceilY = 0.24 + (hf + 1) * floorH - 0.18;

        if (floorHeating[hf] === 'floor') {
          var floorY = 0.24 + hf * floorH + 0.06;
          var mStartY = hf === 0 ? 0.85 : 0.24 + hf * floorH + 0.3;
          addTube(houseGroup, [techX - 0.2, mStartY, -D / 2 + 0.18], [techX - 0.2, floorY, -D / 2 + 0.18], 0.03, heatColor);

          var loopsPerSide = Math.max(4, Math.round(W * 0.7));
          var xStart = -W * 0.42;
          var xEnd = W * 0.42;
          var zStart = -D * 0.38;
          var zEnd = D * 0.38;
          var stepX = (xEnd - xStart) / loopsPerSide;

          var pts = [[techX - 0.2, floorY, -D / 2 + 0.18]];
          for (var i = 0; i <= loopsPerSide; i++) {
            var x = xStart + i * stepX;
            if (i % 2 === 0) {
              pts.push([x, floorY, zStart]);
              pts.push([x, floorY, zEnd]);
            } else {
              pts.push([x, floorY, zEnd]);
              pts.push([x, floorY, zStart]);
            }
          }
          for (var p = 0; p < pts.length - 1; p++) {
            addTube(houseGroup, pts[p], pts[p + 1], 0.021, heatColor);
          }
        } else {
          // Радиаторы: по одному на каждую из 4 стен
          var radY = 0.24 + hf * floorH + 0.75;
          var inset = 0.25;
          var rectPoints = [
            [-W / 2 + inset, ceilY, -D / 2 + inset],
            [W / 2 - inset, ceilY, -D / 2 + inset],
            [W / 2 - inset, ceilY, D / 2 - inset],
            [-W / 2 + inset, ceilY, D / 2 - inset],
            [-W / 2 + inset, ceilY, -D / 2 + inset]
          ];
          for (var rp = 0; rp < rectPoints.length - 1; rp++) {
            addTube(houseGroup, rectPoints[rp], rectPoints[rp + 1], 0.018, heatColor);
          }

          var radiatorSpecs = [
            { x: 0, z: -D / 2 + 0.16, w: 0.9, d: 0.12 },
            { x: W / 2 - 0.16, z: 0, w: 0.12, d: 0.9 },
            { x: 0, z: D / 2 - 0.16, w: 0.9, d: 0.12 },
            { x: -W / 2 + 0.16, z: 0, w: 0.12, d: 0.9 }
          ];
          radiatorSpecs.forEach(function (spec) {
            var radiator = new THREE.Mesh(
              new THREE.BoxGeometry(spec.w, 0.45, spec.d),
              new THREE.MeshBasicMaterial({ color: heatColor })
            );
            radiator.position.set(spec.x, radY, spec.z);
            houseGroup.add(radiator);
            addTube(houseGroup, [spec.x, ceilY, spec.z], [spec.x, radY + 0.22, spec.z], 0.016, heatColor);
          });
        }
      }
    }

    // ============ СЕТЬ 3: ВОДА / КАНАЛИЗАЦИЯ ============
    if (state.systems.water) {
      var waterColor = 0x4fc3ff;
      var baseY = 0.24;

      var pump = new THREE.Mesh(
        new THREE.CylinderGeometry(0.17, 0.17, 0.6, 12),
        new THREE.MeshBasicMaterial({ color: waterColor })
      );
      pump.position.set(techX, baseY + 0.4, techZ);
      houseGroup.add(pump);

      var wetZones = [
        [-W * 0.3, -D * 0.15, 0],
        [W * 0.28, -D * 0.25, 0],
        [-W * 0.3, -D * 0.15, floors === 2 ? 1 : 0]
      ];
      if (floors === 1 && state.baths >= 2) {
        wetZones[2] = [-W * 0.28, D * 0.24, 0];
      }
      if (state.baths === 3) {
        wetZones.push([W * 0.25, D * 0.24, floors === 2 ? 1 : 0]);
      }

      var activeZones = state.baths + 1; // санузлы + кухня
      for (var z = 0; z < Math.min(wetZones.length, activeZones); z++) {
        var zone = wetZones[z];
        var zx = zone[0];
        var zz = zone[1];
        var zFloor = zone[2];
        var targetY = baseY + zFloor * floorH + 0.45;

        addTube(houseGroup, [techX, baseY + 0.15, techZ], [zx, baseY + 0.15, techZ], 0.026, waterColor);
        addTube(houseGroup, [zx, baseY + 0.15, techZ], [zx, baseY + 0.15, zz], 0.026, waterColor);
        addTube(houseGroup, [zx, baseY + 0.15, zz], [zx, targetY, zz], 0.032, waterColor);

        var fixture = new THREE.Mesh(
          new THREE.BoxGeometry(0.32, 0.26, 0.32),
          new THREE.MeshBasicMaterial({ color: waterColor, wireframe: true })
        );
        fixture.position.set(zx, targetY, zz);
        houseGroup.add(fixture);
      }

      addTube(houseGroup, [techX, baseY - 0.04, techZ], [W * 0.48, baseY - 0.04, techZ], 0.045, waterColor);
    }
  }

  function destroyThree() {
    stopLoop();
    if (stageResizeObserver) {
      stageResizeObserver.disconnect();
      stageResizeObserver = null;
    }
    if (houseGroup) disposeGroup(houseGroup);
    if (gridHelper) {
      if (gridHelper.geometry) gridHelper.geometry.dispose();
      if (gridHelper.material) gridHelper.material.dispose();
    }
    if (renderer) {
      renderer.dispose();
      if (renderer.forceContextLoss) renderer.forceContextLoss();
    }
    sceneReady = false;
    scene = null;
    camera = null;
    renderer = null;
    houseGroup = null;
  }

  /* ------------------------------------------------------------
     Наблюдатели: ленивая загрузка и пауза рендера
     ------------------------------------------------------------ */
  var calcOpenTracked = false;

  if ('IntersectionObserver' in window) {
    var lazyObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        if (!calcOpenTracked) {
          calcOpenTracked = true;
          reachGoal('calc_open');
        }
        loadThree();
        lazyObserver.disconnect();
      });
    }, { rootMargin: '400px 0px' });
    lazyObserver.observe(section);

    var visibilityObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        sceneVisible = entry.isIntersecting;
        if (sceneVisible && sceneReady) startLoop();
        if (!sceneVisible) stopLoop();
      });
    }, { threshold: 0 });
    visibilityObserver.observe(section);
  } else {
    loadThree();
  }

  window.addEventListener('pagehide', function (e) {
    if (!e.persisted) destroyThree();
  });

  /* ------------------------------------------------------------
     Инициализация
     ------------------------------------------------------------ */
  restoreParams();
  updateUI();
  ensureTurnstile();
})();
