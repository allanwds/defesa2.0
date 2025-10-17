// accessibility.js
// Simple Text-to-Speech widget using the Web Speech API
(function(){
  if(!('speechSynthesis' in window)) return; // API not supported

  const synth = window.speechSynthesis;
  let voices = [];
  function loadVoices(){
    voices = synth.getVoices();
  }
  loadVoices();
  if(speechSynthesis.onvoiceschanged !== undefined){
    speechSynthesis.onvoiceschanged = loadVoices;
  }

  function speak(text){
    if(!text) return;
    cancel();
    const utter = new SpeechSynthesisUtterance(text);
    // Prefer Portuguese BR if available
    utter.lang = 'pt-BR';
    const br = voices.find(v=>/pt[- ]?br/i.test(v.lang) || /portuguese/i.test(v.name));
    if(br) utter.voice = br;
    utter.rate = 1;
    utter.pitch = 1;
    synth.speak(utter);
    window._a11ySpeaking = true;
    utter.onend = ()=>{ window._a11ySpeaking = false; updateButtonState(); };
  }

  function cancel(){
    if(synth.speaking || synth.pending) synth.cancel();
    window._a11ySpeaking = false;
    updateButtonState();
  }

  function getDocumentText(){
    // Gather visible meaningful text: headings, paragraphs, buttons, labels, table headers/cells
    const selectors = 'h1,h2,h3,h4,h5,h6,p,li,label,button,a,td,th,span';
    const nodes = Array.from(document.querySelectorAll(selectors));
    const visibleTexts = nodes
      .filter(n=>{ const s=getComputedStyle(n); return s && s.display!=='none' && s.visibility!=='hidden'; })
      .map(n=>n.innerText.trim())
      .filter(t=>t.length>0);
    // de-duplicate and join
    const uniq = Array.from(new Set(visibleTexts));
    return uniq.join('. ');
  }

  function updateButtonState(){
    const btn = document.getElementById('a11y-btn');
    if(!btn) return;
    btn.setAttribute('aria-pressed', !!window._a11ySpeaking);
    btn.title = window._a11ySpeaking ? 'Parar leitura' : 'Ler página em voz alta';
    btn.innerText = window._a11ySpeaking ? '🔈' : '🔊';
  }

  // Create control actions
  window.A11y = {
    toggleRead: function(){
      if(window._a11ySpeaking) { cancel(); }
      else { speak(getDocumentText()); }
    },
    readSelection: function(){
      const sel = window.getSelection().toString().trim();
      if(sel) speak(sel); else speak(getDocumentText());
    },
    stop: cancel
  };

  // attach to button when DOM ready
  document.addEventListener('DOMContentLoaded', function(){
    const btn = document.getElementById('a11y-btn');
    if(!btn) return;
    btn.addEventListener('click', function(e){
      e.preventDefault();
      window.A11y.toggleRead();
    });
    btn.addEventListener('contextmenu', function(e){
      // right-click to read selected text
      e.preventDefault();
      window.A11y.readSelection();
    });
    updateButtonState();
  });

})();
