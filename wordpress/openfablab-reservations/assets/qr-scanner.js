/* Existing OpenFabLab/jsQR decoder and four-digit badges, browser-only.
 * The QR replaces the identifier field, never the additional identity check. */
(function () {
  'use strict';
  window.OpenFabLabQR = function (host, input, onRead) {
    let generation = 0, stream, frame, devices = [], deviceIndex = -1;
    function stop() {
      generation++;
      cancelAnimationFrame(frame);
      if (stream) stream.getTracks().forEach(track => track.stop());
      stream = null;
      const video = host.querySelector('video');
      if (video) {video.pause(); video.srcObject = null;}
      host.replaceChildren(); host.hidden = true;
    }
    const hide = () => {if (document.hidden) stop();};
    window.addEventListener('pagehide', stop);
    document.addEventListener('visibilitychange', hide);
    function item(tag, text) {const el = document.createElement(tag); if (text) el.textContent = text; return el;}
    async function start(deviceId) {
      stop(); host.hidden = false;
      const current = generation;
      const message = item('p', 'Présentez votre badge ou votre QR Code devant la caméra.');
      message.setAttribute('role', 'status'); host.appendChild(message);
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || !window.jsQR) {
        message.textContent = 'Caméra indisponible. Vous pouvez saisir votre identifiant.'; return;
      }
      const video = item('video'); video.muted = true; video.setAttribute('playsinline', '');
      video.setAttribute('aria-label', 'Aperçu de la caméra, traité uniquement sur votre appareil');host.appendChild(video);
      const close = item('button', 'Fermer le scanner');close.type = 'button';close.className = 'openfablab-secondary';
      close.addEventListener('click', stop);host.appendChild(close);
      try {
        let received;
        try {
          received = await navigator.mediaDevices.getUserMedia({audio:false, video:deviceId ? {deviceId:{exact:deviceId}} : {facingMode:{exact:'user'}}});
        } catch (error) {
          if (deviceId || !['OverconstrainedError', 'NotFoundError'].includes(error.name)) throw error;
          if (current !== generation) return;
          received = await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:'user'}}});
        }
        // Closing while the permission prompt is open must also stop the late stream.
        if (current !== generation || !host.isConnected) {received.getTracks().forEach(track => track.stop());return;}
        stream = received;video.srcObject = stream;await video.play();
        if (current !== generation) return;
        try {devices = (await navigator.mediaDevices.enumerateDevices()).filter(device => device.kind === 'videoinput');} catch (_) {devices = [];}
        if (current !== generation) return;
        const actual = stream.getVideoTracks()[0]?.getSettings().deviceId;
        deviceIndex = devices.findIndex(device => device.deviceId === actual);
        if (devices.length > 1) {
          const change = item('button', 'Changer de caméra');change.type = 'button';change.className = 'openfablab-secondary';
          change.addEventListener('click', () => start(devices[(deviceIndex + 1) % devices.length].deviceId));host.appendChild(change);
        }
        const canvas = item('canvas'), context = canvas.getContext('2d', {willReadFrequently:true});
        let last = 0;
        const scan = now => {
          if (current !== generation) return;
          if (!host.isConnected) {stop();return;}
          if (video.readyState >= 2 && video.videoWidth && now - last >= 160) {
            last = now;canvas.width = Math.min(720, video.videoWidth);canvas.height = Math.round(video.videoHeight * canvas.width / video.videoWidth);
            context.drawImage(video, 0, 0, canvas.width, canvas.height);
            const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
            const found = window.jsQR(pixels.data, canvas.width, canvas.height, {inversionAttempts:'attemptBoth'});
            if (found) {
              const id = found.data.trim();
              if (/^[0-9]{4}$/.test(id)) {input.value = id;input.dispatchEvent(new Event('input', {bubbles:true}));stop();onRead(id);return;}
              message.textContent = 'Ce QR Code n’est pas un badge OpenFabLab. Essayez à nouveau ou saisissez votre identifiant.';
            }
          }
          frame = requestAnimationFrame(scan);
        };
        frame = requestAnimationFrame(scan);
      } catch (error) {
        if (current !== generation) return;
        stop();host.hidden = false;
        const messages = {NotAllowedError:'L’accès à la caméra a été refusé.', NotFoundError:'Aucune caméra disponible.', NotReadableError:'La caméra est déjà utilisée ou indisponible.'};
        const note = item('p', (messages[error.name] || 'Le scanner est indisponible.') + ' Vous pouvez saisir votre identifiant.');note.setAttribute('role','status');host.appendChild(note);
      }
    }
    return {start, stop, destroy() {stop();window.removeEventListener('pagehide',stop);document.removeEventListener('visibilitychange',hide);}};
  };
}());
