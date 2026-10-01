"use strict";

(function enableQrScanner() {
    const scanner = document.querySelector("[data-qr-scanner]");
    if (!scanner) return;

    const startButton = scanner.querySelector("[data-qr-start]");
    const camera = scanner.querySelector("[data-qr-camera]");
    const video = scanner.querySelector("[data-qr-video]");
    const canvas = scanner.querySelector("[data-qr-canvas]");
    const status = scanner.querySelector("[data-qr-status]");
    const form = scanner.querySelector("[data-qr-form]");
    const publicIdInput = scanner.querySelector("[data-qr-public-id]");
    const manualIdentifierInput = document.querySelector("#public-id");

    if (
        !startButton ||
        !camera ||
        !video ||
        !canvas ||
        !status ||
        !form ||
        !publicIdInput
    ) {
        return;
    }

    let mediaStream = null;
    let animationFrame = null;
    let scanning = false;
    let starting = false;
    let stoppedByUser = false;
    let lastScanTime = 0;

    function setStatus(message, state = "") {
        status.textContent = message;
        status.dataset.state = state;
    }

    function stopCamera(keepStatus = false, userRequested = false) {
        scanning = false;
        starting = false;
        if (userRequested) stoppedByUser = true;
        if (animationFrame !== null) {
            window.cancelAnimationFrame(animationFrame);
            animationFrame = null;
        }
        if (mediaStream) {
            mediaStream.getTracks().forEach((track) => track.stop());
            mediaStream = null;
        }
        video.srcObject = null;
        camera.hidden = true;
        startButton.hidden = !userRequested;
        startButton.disabled = false;
        if (!keepStatus) {
            setStatus("Caméra fermée. Vous pouvez saisir votre identifiant ou la rouvrir.");
        }
    }

    function submitScannedIdentifier(publicId) {
        setStatus(`Identifiant ${publicId} reconnu. Enregistrement en cours…`, "success");
        publicIdInput.value = publicId;
        stopCamera(true);
        if (typeof form.requestSubmit === "function") {
            form.requestSubmit();
        } else {
            form.submit();
        }
    }

    function scanVideoFrame(timestamp) {
        if (!scanning) return;

        // Environ six analyses par seconde suffisent et limitent la charge tablette.
        if (timestamp - lastScanTime < 160) {
            animationFrame = window.requestAnimationFrame(scanVideoFrame);
            return;
        }
        lastScanTime = timestamp;

        if (
            video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA &&
            video.videoWidth > 0 &&
            video.videoHeight > 0
        ) {
            const maximumWidth = 720;
            const scale = Math.min(1, maximumWidth / video.videoWidth);
            const width = Math.max(1, Math.round(video.videoWidth * scale));
            const height = Math.max(1, Math.round(video.videoHeight * scale));

            if (canvas.width !== width || canvas.height !== height) {
                canvas.width = width;
                canvas.height = height;
            }

            const context = canvas.getContext("2d", { willReadFrequently: true });
            if (context) {
                context.drawImage(video, 0, 0, width, height);
                const image = context.getImageData(0, 0, width, height);
                const result = window.jsQR(image.data, width, height, {
                    inversionAttempts: "attemptBoth",
                });

                if (result) {
                    const scannedValue = result.data.trim();
                    if (/^[0-9]{4}$/.test(scannedValue)) {
                        submitScannedIdentifier(scannedValue);
                        return;
                    }
                    setStatus(
                        "Ce QR code ne contient pas un identifiant OpenFabLab à 4 chiffres.",
                        "error",
                    );
                }
            }
        }

        animationFrame = window.requestAnimationFrame(scanVideoFrame);
    }

    async function startCamera() {
        if (starting || scanning) return;
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            startButton.hidden = false;
            setStatus(
                "La caméra n'est pas disponible. Ouvrez l'adresse HTTPS de votre FabLab ou saisissez votre identifiant.",
                "error",
            );
            return;
        }
        if (typeof window.jsQR !== "function") {
            startButton.hidden = false;
            setStatus(
                "Le lecteur QR n'a pas pu démarrer. Saisissez votre identifiant à 4 chiffres.",
                "error",
            );
            return;
        }

        starting = true;
        stoppedByUser = false;
        startButton.disabled = true;
        startButton.hidden = true;
        setStatus("Ouverture de la caméra avant…");

        try {
            const videoPreferences = {
                width: { ideal: 1280 },
                height: { ideal: 720 },
            };
            try {
                // La caméra avant est imposée en premier pour la tablette d'accueil.
                mediaStream = await navigator.mediaDevices.getUserMedia({
                    audio: false,
                    video: {
                        ...videoPreferences,
                        facingMode: { exact: "user" },
                    },
                });
            } catch (preferredCameraError) {
                if (
                    !preferredCameraError ||
                    !["OverconstrainedError", "NotFoundError"].includes(
                        preferredCameraError.name,
                    )
                ) {
                    throw preferredCameraError;
                }
                // Secours pour les anciens navigateurs qui gèrent mal « exact ».
                mediaStream = await navigator.mediaDevices.getUserMedia({
                    audio: false,
                    video: {
                        ...videoPreferences,
                        facingMode: { ideal: "user" },
                    },
                });
            }
            video.srcObject = mediaStream;
            await video.play();
            const videoTrack = mediaStream.getVideoTracks()[0];
            const cameraSettings =
                videoTrack && typeof videoTrack.getSettings === "function"
                    ? videoTrack.getSettings()
                    : {};
            camera.dataset.facingMode = cameraSettings.facingMode || "user";
            camera.hidden = false;
            startButton.hidden = true;
            startButton.disabled = false;
            starting = false;
            scanning = true;
            lastScanTime = 0;
            setStatus("", "active");
            animationFrame = window.requestAnimationFrame(scanVideoFrame);
        } catch (error) {
            stopCamera(true);
            startButton.hidden = false;
            if (error && error.name === "NotAllowedError") {
                setStatus(
                    "Accès à la caméra refusé. Autorisez la caméra dans le navigateur puis réessayez.",
                    "error",
                );
            } else if (error && error.name === "NotFoundError") {
                setStatus(
                    "Aucune caméra n'a été trouvée. Saisissez votre identifiant à 4 chiffres.",
                    "error",
                );
            } else {
                setStatus(
                    "La caméra n'a pas pu démarrer. Réessayez ou saisissez votre identifiant.",
                    "error",
                );
            }
        }
    }

    startButton.addEventListener("click", startCamera);
    // Toucher le champ manuel ferme naturellement la caméra : aucun bouton
    // supplémentaire n'est nécessaire dans le parcours normal.
    if (manualIdentifierInput) {
        manualIdentifierInput.addEventListener("focus", () => stopCamera(true, true));
    }
    window.addEventListener("pagehide", () => stopCamera(true));
    document.addEventListener("visibilitychange", () => {
        if (document.hidden && (scanning || starting)) {
            stopCamera(true);
        } else if (!document.hidden && !stoppedByUser && !scanning) {
            startCamera();
        }
    });

    // Le clic « Je suis usager » constitue déjà l'action volontaire : le scan
    // démarre dès l'arrivée sur cette page, sans imposer un second bouton.
    startCamera();
})();
