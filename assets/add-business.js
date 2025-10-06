// FILE: assets/add-business.js
(function () {
  const form = document.getElementById('addBusinessForm');
  if (!form) return;

  const msg = document.getElementById('formMsg');

  function setMsg(text, ok) {
    msg.textContent = text;
    msg.className = 'form-msg ' + (ok ? 'ok' : 'err');
  }

  form.addEventListener('submit', async (e) => {
    // Basic HTML5 checks first
    if (!form.checkValidity()) {
      // Let the browser show native validation bubbles
      return;
    }
    e.preventDefault();

    setMsg('Submitting…', true);

    try {
      const data = new FormData(form);

      // If you don’t need file uploads, you can send JSON instead
      const res = await fetch(form.action, {
        method: 'POST',
        body: data
      });

      if (res.ok) {
        form.reset();
        setMsg('Thanks! Your application has been received. We’ll be in touch soon.', true);
      } else {
        setMsg('Sorry—something went wrong. Please try again in a moment.', false);
      }
    } catch (err) {
      setMsg('Network error. Please check your connection and try again.', false);
    }
  });
})();
