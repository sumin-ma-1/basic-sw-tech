/* composer_bind.js — Excel: original clip_bind styling; main chat: same shell, no clip icon */
(function () {
  const doc = window.parent.document;
  const win = window.parent;

  function uploaderRoot() {
    const root = doc.getElementById("bst-excel-composer");
    if (!root) return null;
    const main = root.closest('section[data-testid="stMain"]') || doc;
    return main.querySelector('[data-testid="stFileUploader"]');
  }

  function openPicker() {
    const box = uploaderRoot();
    if (!box) return;
    const input = box.querySelector('input[type="file"]');
    if (input) {
      input.click();
      return;
    }
    const browse = box.querySelector("button");
    if (browse) browse.click();
  }

  /* Original clip_bind.js — pill on [clip | input] horizontal block only */
  function styleUnifiedInput(hBlock) {
    if (!hBlock) return false;

    hBlock.style.setProperty("border", "1px solid var(--bst-border-strong)", "important");
    hBlock.style.setProperty("border-radius", "22px", "important");
    hBlock.style.setProperty("background", "var(--bst-surface-elevated)", "important");
    hBlock.style.setProperty("box-shadow", "var(--bst-shadow-sm)", "important");
    hBlock.style.setProperty("gap", "0", "important");
    hBlock.style.setProperty("padding", "0 6px 0 8px", "important");
    hBlock.style.setProperty("overflow", "hidden", "important");
    hBlock.style.alignItems = "center";

    hBlock.querySelectorAll("div").forEach(function (el) {
      if (el === hBlock) return;
      el.style.setProperty("background", "transparent", "important");
      el.style.setProperty("border", "none", "important");
      el.style.setProperty("box-shadow", "none", "important");
      el.style.setProperty("padding", "0", "important");
      el.style.setProperty("margin", "0", "important");
      el.style.setProperty("gap", "0", "important");
    });

    var ta = hBlock.querySelector("textarea");
    if (ta) {
      ta.style.setProperty("border", "none", "important");
      ta.style.setProperty("box-shadow", "none", "important");
      ta.style.setProperty("border-radius", "0", "important");
      ta.style.setProperty("background", "var(--bst-surface-elevated)", "important");
    }

    var sendBtn =
      hBlock.querySelector('[data-testid*="Submit"]') ||
      hBlock.querySelector('[data-testid="stChatInput"] button');
    if (sendBtn) {
      Object.assign(sendBtn.style, {
        width: "2.2rem",
        height: "2.2rem",
        minHeight: "0",
        borderRadius: "50%",
        padding: "0",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: "0",
        marginRight: "6px",
      });

      function updateBtnAlign() {
        var multi = ta && ta.offsetHeight > 60;
        sendBtn.style.alignSelf = multi ? "flex-end" : "center";
        sendBtn.style.marginBottom = multi ? "9px" : "0";
      }

      if (ta && !ta.dataset.bstBtnAlign) {
        ta.dataset.bstBtnAlign = "1";
        ta.addEventListener("input", updateBtnAlign);
      }
      updateBtnAlign();
    }

    var inputCol = hBlock.querySelector('[data-testid="column"]:last-child');
    if (inputCol) {
      inputCol.style.setProperty("flex", "1 1 0", "important");
      inputCol.style.setProperty("padding", "0", "important");
      inputCol.style.setProperty("min-width", "0", "important");
    }

    return true;
  }

  function styleLeadingColumn(col, isClip) {
    if (!col) return;
    var w = "38px";
    col.style.setProperty("flex", "0 0 " + w, "important");
    col.style.setProperty("width", w, "important");
    col.style.setProperty("min-width", w, "important");
    col.style.setProperty("max-width", w, "important");
    col.style.setProperty("padding", "0", "important");
    Object.assign(col.style, {
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
    });
    if (!isClip) return;
    var clipWrap = col.querySelector('[class*="st-key-excel_clip_btn"]');
    if (!clipWrap) return;
    col.querySelectorAll('[data-testid="stTooltipHoverTarget"]').forEach(function (tt) {
      tt.style.setProperty("width", "auto", "important");
      tt.style.setProperty("justify-content", "center", "important");
      tt.style.setProperty("flex", "0 0 auto", "important");
    });
    clipWrap.querySelectorAll(
      '[data-testid="stVerticalBlockBorderWrapper"],[data-testid="stVerticalBlock"],' +
        '[data-testid="stElementContainer"],.stButton'
    ).forEach(function (el) {
      Object.assign(el.style, {
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        margin: "0",
        padding: "0",
        minHeight: "0",
        width: "100%",
      });
    });
  }

  function styleExcelComposer() {
    var root = doc.getElementById("bst-excel-composer");
    if (!root) return false;
    var main = root.closest('section[data-testid="stMain"]') || doc;
    var clipWrap = main.querySelector('[class*="st-key-excel_clip_btn"]');
    if (!clipWrap || !clipWrap.getBoundingClientRect().width) return false;

    var hBlock = clipWrap.closest('[data-testid="stHorizontalBlock"]');
    if (!hBlock) return false;

    styleUnifiedInput(hBlock);
    styleLeadingColumn(clipWrap.closest('[data-testid="column"]'), true);
    return true;
  }

  function findMainChatComposerRoot() {
    if (!doc.getElementById("bst-chat-composer")) return null;
    if (doc.getElementById("bst-excel-composer")) return null;

    var marker = doc.getElementById("bst-chat-composer");
    var wrap = marker.closest(".stElementContainer");
    var sib = wrap && wrap.nextElementSibling;
    for (var i = 0; i < 16 && sib; i += 1) {
      var ci = sib.querySelector('[data-testid="stChatInput"]');
      if (ci && ci.querySelector("textarea")) return ci;
      sib = sib.nextElementSibling;
    }
    return null;
  }

  function layoutMainChatPillInterior(chatInput) {
    if (!chatInput || chatInput.getAttribute("data-testid") !== "stChatInput") return;

    chatInput.style.setProperty("display", "flex", "important");
    chatInput.style.setProperty("flex-direction", "column", "important");
    chatInput.style.setProperty("align-items", "stretch", "important");
    chatInput.style.setProperty("width", "100%", "important");
    chatInput.style.setProperty("max-width", "100%", "important");
    chatInput.style.setProperty("box-sizing", "border-box", "important");

    var vWrap = chatInput.querySelector(
      '[data-testid="stVerticalBlockBorderWrapper"]'
    );
    if (vWrap) {
      vWrap.style.setProperty("flex", "1 1 auto", "important");
      vWrap.style.setProperty("width", "100%", "important");
      vWrap.style.setProperty("min-width", "0", "important");
      vWrap.style.setProperty("display", "flex", "important");
      vWrap.style.setProperty("flex-direction", "column", "important");
      vWrap.style.setProperty("background", "transparent", "important");
    }

    var innerRow = chatInput.querySelector('[data-testid="stHorizontalBlock"]');
    if (!innerRow) return;

    innerRow.style.setProperty("display", "flex", "important");
    innerRow.style.setProperty("flex-direction", "row", "important");
    innerRow.style.setProperty("align-items", "center", "important");
    innerRow.style.setProperty("width", "100%", "important");
    innerRow.style.setProperty("flex", "1 1 auto", "important");
    innerRow.style.setProperty("min-width", "0", "important");
    innerRow.style.setProperty("gap", "0", "important");

    var ta = chatInput.querySelector("textarea");
    var sendBtn =
      chatInput.querySelector('[data-testid*="ChatInputSubmitButton"]') ||
      chatInput.querySelector('[data-testid*="Submit"]') ||
      chatInput.querySelector("button[type='submit']") ||
      chatInput.querySelector("button");

    if (ta) {
      ta.style.setProperty("flex", "1 1 auto", "important");
      ta.style.setProperty("width", "100%", "important");
      ta.style.setProperty("min-width", "0", "important");
      ta.style.setProperty("padding-right", "8px", "important");
    }

    if (sendBtn) {
      var w = sendBtn.parentElement;
      while (w && w !== innerRow) {
        w.style.setProperty("flex", "0 0 auto", "important");
        w.style.setProperty("position", "static", "important");
        w.style.setProperty("right", "auto", "important");
        w.style.setProperty("bottom", "auto", "important");
        w.style.setProperty("top", "auto", "important");
        w.style.setProperty("left", "auto", "important");
        w.style.setProperty("transform", "none", "important");
        w = w.parentElement;
      }
      sendBtn.style.setProperty("position", "static", "important");
      sendBtn.style.setProperty("flex-shrink", "0", "important");
    }
  }

  function styleMainChatComposer() {
    var root = findMainChatComposerRoot();
    if (!root) return false;

    styleUnifiedInput(root);
    layoutMainChatPillInterior(root);
    return true;
  }

  function bindClip() {
    const clipBtn = doc.querySelector('[class*="st-key-excel_clip_btn"] button');
    if (!uploaderRoot() || !clipBtn || clipBtn.dataset.bstClipBound === "1") return;
    clipBtn.dataset.bstClipBound = "1";
    clipBtn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      openPicker();
    });
  }

  function run() {
    var didExcel = styleExcelComposer();
    var didChat = styleMainChatComposer();
    if (didExcel) bindClip();
    return didExcel || didChat;
  }

  [50, 150, 300, 500, 800, 1500, 2500].forEach(function (ms) {
    setTimeout(run, ms);
  });

  if (!win.__bstComposerBind) {
    win.__bstComposerBind = true;
    new MutationObserver(function () {
      requestAnimationFrame(run);
    }).observe(doc.body, { childList: true, subtree: true });
  }
  run();
})();
