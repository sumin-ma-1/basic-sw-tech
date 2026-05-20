/* chip_styles.js — Hub Excel 진입/종료 칩 스타일 페인트
   components.html iframe 에서 실행, window.parent.document 를 대상으로 함 */
(function () {
  var d   = window.parent.document;
  var win = window.parent;

  var dark = function () {
    return d.documentElement.getAttribute('data-theme') === 'dark';
  };

  var pal = function () {
    return dark() ? {
      bg:  'rgba(13,148,136,0.14)', bd: 'rgba(45,212,191,0.48)', fg: '#5eead4',
      hbg: 'rgba(45,212,191,0.26)', hbd: '#2dd4bf',              hfg: '#ccfbf1',
      sh:  '0 1px 4px rgba(13,148,136,.28)'
    } : {
      bg:  '#ccfbf1', bd: '#5eead4', fg: '#0f766e',
      hbg: '#99f6e4', hbd: '#2dd4bf', hfg: '#115e59',
      sh:  '0 1px 3px rgba(13,148,136,.14)'
    };
  };

  var s = function (b, k, v) { b && b.style.setProperty(k, v, 'important'); };

  var paint = function (btn, isExit) {
    if (!btn) return;
    var c  = pal();
    var dk = dark();

    s(btn, 'background', dk
      ? 'linear-gradient(180deg,rgba(45,212,191,.16) 0%,' + c.bg + ' 100%)'
      : 'linear-gradient(180deg,#f0fdfa 0%,#ccfbf1 100%)');
    s(btn, 'background-color', c.bg);
    s(btn, 'border',       '1px solid ' + c.bd);
    s(btn, 'color',        c.fg);
    s(btn, 'font-weight',  '600');
    s(btn, 'border-radius','999px');
    s(btn, 'box-shadow',   '0 1px 0 rgba(255,255,255,.55) inset, ' + c.sh);
    s(btn, 'filter',       'none');
    s(btn, 'transform',    isExit ? 'none' : 'translateY(0)');

    if (isExit) {
      s(btn, 'width',           '2.4rem');
      s(btn, 'height',          '2.4rem');
      s(btn, 'min-height',      '2.4rem');
      s(btn, 'padding',         '0');
      s(btn, 'display',         'flex');
      s(btn, 'align-items',     'center');
      s(btn, 'justify-content', 'center');
      s(btn, 'font-size',       '1.15rem');
      s(btn, 'line-height',     '1');
    }

    btn.querySelectorAll('p,span').forEach(function (n) {
      s(n, 'color', 'inherit');
    });

    /* 이벤트 리스너 + 버튼 자체 MutationObserver 는 최초 1회만 등록 */
    if (!btn.dataset.bstExcelFx) {
      btn.dataset.bstExcelFx = '1';

      btn.addEventListener('mouseenter', function () {
        var h = pal();
        s(btn, 'background-color', h.hbg);
        s(btn, 'border-color',     h.hbd);
        s(btn, 'color',            h.hfg);
        if (!isExit) {
          s(btn, 'transform',  'translateY(-2px)');
          s(btn, 'box-shadow',
            '0 1px 0 rgba(255,255,255,.45) inset, ' +
            '0 2px 8px rgba(13,148,136,.22), ' +
            '0 4px 14px rgba(13,148,136,.24)');
        }
      });

      btn.addEventListener('mouseleave', function () { paint(btn, isExit); });

      /* React re-render 시 class 변경을 감지해 스타일 재적용
         style 은 제외 — paint() 가 style 을 수정하므로 포함하면 무한루프 발생 */
      new MutationObserver(function () {
        paint(btn, isExit);
      }).observe(btn, { attributes: true, attributeFilter: ['class'] });
    }
  };

  var after = function (id) {
    var a = d.getElementById(id);
    if (!a) return null;
    var n = a.nextElementSibling;
    for (var i = 0; i < 6 && n; i++) {
      var b = n.querySelector && n.querySelector('button');
      if (b) return b;
      n = n.nextElementSibling;
    }
    return null;
  };

  var run = function () {
    d.querySelectorAll('[class*="st-key-hub_enter_excel"]').forEach(function (w) {
      paint(w.matches('button') ? w : w.querySelector('button'), false);
    });
    d.querySelectorAll('[class*="st-key-hub_exit_excel"]').forEach(function (w) {
      paint(w.matches('button') ? w : w.querySelector('button'), true);
    });
    paint(after('bst-mode-toggle-chat'),  false);
    paint(after('bst-mode-toggle-excel'), true);
  };

  /* window.parent 에 run 저장 → resize 리스너가 iframe 재생성 후에도 최신 run 호출 */
  win.__bstChipRun = run;

  run();
  new MutationObserver(run).observe(d.body, { childList: true, subtree: true });
  setTimeout(run, 30);
  setTimeout(run, 200);
  setTimeout(run, 700);

  if (!win.__bstChipResizeBound) {
    win.__bstChipResizeBound = true;
    win.addEventListener('resize', function () {
      var r = win.__bstChipRun;
      if (r) { setTimeout(r, 150); setTimeout(r, 400); }
    });
  }
})();
