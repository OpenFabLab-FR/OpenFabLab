"use strict";

function updateParisClock() {
    const clock = document.querySelector("[data-paris-clock]");
    if (!clock) return;

    const now = new Date();
    const formatter = new Intl.DateTimeFormat("fr-FR", {
        timeZone: "Europe/Paris",
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });

    const formatted = formatter.format(now);
    clock.textContent = formatted.charAt(0).toUpperCase() + formatted.slice(1);
    clock.dateTime = now.toISOString();
}

function enableUserSearch() {
    const searchInput = document.querySelector("[data-user-search]");
    const cards = [...document.querySelectorAll("[data-user-card]")];
    const noResult = document.querySelector("[data-no-search-result]");
    if (!searchInput || cards.length === 0) return;

    searchInput.addEventListener("input", () => {
        const query = searchInput.value.trim().toLocaleLowerCase("fr");
        let visibleCount = 0;

        cards.forEach((card) => {
            const name = card.dataset.searchText.toLocaleLowerCase("fr");
            const isVisible = name.includes(query);
            card.hidden = !isVisible;
            if (isVisible) visibleCount += 1;
        });

        if (noResult) noResult.hidden = visibleCount !== 0;
    });
}

function dismissFlashMessages() {
    document.querySelectorAll("[data-auto-dismiss]").forEach((message) => {
        window.setTimeout(() => {
            message.classList.add("is-hiding");
            window.setTimeout(() => message.remove(), 350);
        }, 5000);
    });
}

function registerApplicationMode() {
    const serviceWorkerUrl = document.documentElement.dataset.serviceWorkerUrl;
    if (!serviceWorkerUrl || !("serviceWorker" in navigator)) return;

    navigator.serviceWorker.register(serviceWorkerUrl).catch(() => {
        // L'application reste entièrement utilisable dans un onglet classique.
    });
}

let screenWakeLock = null;

function parisMinutesNow() {
    try {
        const formatter = new Intl.DateTimeFormat("fr-FR", {
            timeZone: "Europe/Paris",
            hour: "2-digit",
            minute: "2-digit",
            hourCycle: "h23",
        });
        const parts = formatter.formatToParts(new Date());
        const hourPart = parts.find((part) => part.type === "hour");
        const minutePart = parts.find((part) => part.type === "minute");
        if (!hourPart || !minutePart) throw new Error("Heure de Paris indisponible");
        return Number(hourPart.value) * 60 + Number(minutePart.value);
    } catch (_error) {
        // Repli pour un très ancien navigateur. La tablette est configurée sur
        // Europe/Paris, son heure locale reste donc une approximation sûre.
        const now = new Date();
        return now.getHours() * 60 + now.getMinutes();
    }
}

function wakeLockScheduleIsActive() {
    const root = document.documentElement;
    const parseTime = (value) => {
        const match = /^(\d{2}):(\d{2})$/.exec(value || "");
        return match ? Number(match[1]) * 60 + Number(match[2]) : null;
    };
    const start = parseTime(root.dataset.wakeLockStart);
    const end = parseTime(root.dataset.wakeLockEnd);
    if (start === null || end === null || start === end) return true;
    const now = parisMinutesNow();
    return start < end ? now >= start && now < end : now >= start || now < end;
}

async function requestScreenWakeLock() {
    if (document.documentElement.dataset.keepScreenAwake !== "1") return;
    if (!wakeLockScheduleIsActive() || screenWakeLock) return;
    if (!("wakeLock" in navigator) || document.visibilityState !== "visible") return;
    try {
        screenWakeLock = await navigator.wakeLock.request("screen");
        screenWakeLock.addEventListener("release", () => {
            screenWakeLock = null;
        });
    } catch (_error) {
        // Le navigateur, l'économie d'énergie ou le système peut refuser l'API.
        // Le compteur reste alors entièrement fonctionnel.
        screenWakeLock = null;
    }
}

async function synchronizeScreenWakeLock() {
    const enabled = document.documentElement.dataset.keepScreenAwake === "1";
    if (enabled && wakeLockScheduleIsActive() && document.visibilityState === "visible") {
        await requestScreenWakeLock();
    } else {
        await releaseScreenWakeLock();
    }
    displayWakeLockCompatibility();
}

async function releaseScreenWakeLock() {
    if (!screenWakeLock) return;
    try {
        await screenWakeLock.release();
    } catch (_error) {
        // Une libération déjà effectuée ne doit jamais gêner l'application.
    } finally {
        screenWakeLock = null;
    }
}

function configureScreenWakeLock() {
    synchronizeScreenWakeLock();
    window.setInterval(synchronizeScreenWakeLock, 30000);

    document.addEventListener("visibilitychange", () => {
        synchronizeScreenWakeLock();
    });
    window.addEventListener("pagehide", releaseScreenWakeLock);
}

function displayWakeLockCompatibility() {
    const status = document.querySelector("[data-wake-lock-status]");
    if (!status) return;
    if (!("wakeLock" in navigator)) {
        status.textContent = "Non pris en charge par ce navigateur";
        return;
    }
    status.textContent = (
        status.dataset.optionEnabled === "1" && wakeLockScheduleIsActive()
    ) ? "Actif" : "Inactif";
}

function configureHomeLiveRefresh() {
    const state = document.querySelector("[data-home-live-state]");
    if (!state || !state.dataset.stateUrl) return;
    let checking = false;

    const checkState = async () => {
        if (checking || document.visibilityState !== "visible") return;
        checking = true;
        try {
            const response = await fetch(state.dataset.stateUrl, {
                cache: "no-store",
                headers: { Accept: "application/json" },
            });
            if (!response.ok) return;
            const payload = await response.json();
            if (
                payload.signature &&
                payload.signature !== state.dataset.stateSignature &&
                !document.body.classList.contains("dialog-open")
            ) {
                window.location.reload();
            }
        } catch (_error) {
            // Une coupure réseau ne gêne pas la borne ; le contrôle suivant réessaie.
        } finally {
            checking = false;
        }
    };

    window.setInterval(checkState, 10000);
    window.setTimeout(() => {
        if (!document.body.classList.contains("dialog-open")) window.location.reload();
    }, 10 * 60 * 1000);
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") checkState();
    });
}

function configureHomeScrollLock() {
    const root = document.documentElement;
    const body = document.body;
    if (
        root.dataset.lockHomeScroll !== "1" ||
        !body.classList.contains("home-page") ||
        !window.matchMedia(
            "(orientation: landscape) and (min-width: 761px) and (min-height: 621px)"
        ).matches
    ) return;

    const updateVisibleHeight = () => {
        const viewportHeight = window.visualViewport
            ? window.visualViewport.height
            : window.innerHeight;
        if (viewportHeight > 0) {
            root.style.setProperty("--home-viewport-height", `${Math.floor(viewportHeight)}px`);
        }
        if (window.scrollX !== 0 || window.scrollY !== 0) window.scrollTo(0, 0);
    };

    const preventVerticalPan = (event) => {
        if (event.target.closest("a, button, input, select, textarea, label")) return;
        if (event.cancelable) event.preventDefault();
    };

    updateVisibleHeight();
    window.addEventListener("resize", updateVisibleHeight);
    window.addEventListener("orientationchange", updateVisibleHeight);
    window.addEventListener("scroll", updateVisibleHeight, { passive: true });
    document.addEventListener("touchmove", preventVerticalPan, { passive: false });
    if (window.visualViewport) {
        window.visualViewport.addEventListener("resize", updateVisibleHeight);
    }
}

function configureIdentifierAutoSubmit() {
    const form = document.querySelector("[data-identifier-form]");
    const input = document.querySelector("[data-identifier-input]");
    const submitButton = document.querySelector("[data-identifier-submit]");
    if (!form || !input || !submitButton) return;

    const submitWhenComplete = () => {
        if (form.dataset.submitting === "1" || !/^\d{4}$/.test(input.value)) return;
        form.requestSubmit(submitButton);
    };

    input.addEventListener("input", () => {
        const sanitizedValue = input.value.replace(/\D/g, "").slice(0, 4);
        if (input.value !== sanitizedValue) input.value = sanitizedValue;
        if (sanitizedValue.length === 4) window.setTimeout(submitWhenComplete, 0);
    });

    form.addEventListener("submit", (event) => {
        if (form.dataset.submitting === "1") {
            event.preventDefault();
            return;
        }
        if (!/^\d{4}$/.test(input.value)) {
            event.preventDefault();
            input.focus();
            return;
        }
        form.dataset.submitting = "1";
        submitButton.disabled = true;
        input.readOnly = true;
    });
}

function configureQuickDeparture() {
    const dialogBackdrop = document.querySelector("[data-departure-dialog]");
    const triggers = document.querySelectorAll("[data-quick-departure]");
    if (!dialogBackdrop || triggers.length === 0) return;

    const form = dialogBackdrop.querySelector("[data-departure-form]");
    const name = dialogBackdrop.querySelector("[data-departure-name]");
    const countdown = dialogBackdrop.querySelector("[data-departure-countdown]");
    const cancelButton = dialogBackdrop.querySelector("[data-departure-cancel]");
    const confirmButton = dialogBackdrop.querySelector("[data-departure-confirm]");
    let countdownTimer = null;
    let remainingSeconds = 10;

    const startThemeProgress = () => {
        dialogBackdrop.style.setProperty("--departure-progress", "0%");
        dialogBackdrop.style.setProperty("--departure-progress-duration", `${remainingSeconds}s`);
        window.requestAnimationFrame(() => {
            window.requestAnimationFrame(() => {
                dialogBackdrop.style.setProperty("--departure-progress", "100%");
            });
        });
    };

    const closeDialog = () => {
        if (countdownTimer) window.clearInterval(countdownTimer);
        countdownTimer = null;
        dialogBackdrop.hidden = true;
        dialogBackdrop.style.removeProperty("--departure-progress");
        dialogBackdrop.style.removeProperty("--departure-progress-duration");
        document.body.classList.remove("dialog-open");
        form.dataset.submitting = "0";
    };

    const submitDeparture = () => {
        if (form.dataset.submitting === "1") return;
        form.dataset.submitting = "1";
        if (countdownTimer) window.clearInterval(countdownTimer);
        countdownTimer = null;
        form.submit();
    };

    const openDialog = (trigger) => {
        form.action = trigger.dataset.departureUrl;
        form.dataset.submitting = "0";
        name.textContent = trigger.dataset.userName;
        remainingSeconds = 10;
        countdown.textContent = remainingSeconds;
        dialogBackdrop.hidden = false;
        document.body.classList.add("dialog-open");
        startThemeProgress();
        cancelButton.focus();

        countdownTimer = window.setInterval(() => {
            remainingSeconds -= 1;
            countdown.textContent = remainingSeconds;
            if (remainingSeconds <= 0) submitDeparture();
        }, 1000);
    };

    triggers.forEach((trigger) => trigger.addEventListener("click", () => openDialog(trigger)));
    cancelButton.addEventListener("click", closeDialog);
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        submitDeparture();
    });
    confirmButton?.addEventListener("click", () => {
        if (countdownTimer) window.clearInterval(countdownTimer);
    });
    dialogBackdrop.addEventListener("click", (event) => {
        if (event.target === dialogBackdrop) closeDialog();
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !dialogBackdrop.hidden) closeDialog();
    });
}

function configureQrPreviews() {
    const dialogBackdrop = document.querySelector("[data-qr-preview-dialog]");
    const triggers = document.querySelectorAll("[data-qr-preview]");
    if (!dialogBackdrop || triggers.length === 0) return;

    const image = dialogBackdrop.querySelector("[data-qr-preview-image]");
    const title = dialogBackdrop.querySelector("[data-qr-preview-title]");
    const closeButton = dialogBackdrop.querySelector("[data-qr-preview-close]");

    const closeDialog = () => {
        dialogBackdrop.hidden = true;
        document.body.classList.remove("dialog-open");
        image.src = "";
    };

    triggers.forEach((trigger) => {
        trigger.addEventListener("click", () => {
            title.textContent = trigger.dataset.qrLabel;
            image.src = trigger.dataset.qrSrc;
            image.alt = trigger.dataset.qrLabel;
            dialogBackdrop.hidden = false;
            document.body.classList.add("dialog-open");
            closeButton.focus();
        });
    });

    closeButton.addEventListener("click", closeDialog);
    dialogBackdrop.addEventListener("click", (event) => {
        if (event.target === dialogBackdrop) closeDialog();
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !dialogBackdrop.hidden) closeDialog();
    });
}

function configureServiceForm() {
    const form = document.querySelector("[data-service-form]");
    const typeSelect = document.querySelector("[data-service-type]");
    if (!form || !typeSelect) return;

    const titleLabel = form.querySelector("[data-service-title-label]");
    const dateLabel = form.querySelector("[data-service-date-label]");
    const updateFields = () => {
        const type = typeSelect.value;
        form.querySelectorAll("[data-service-fields]").forEach((field) => {
            const group = field.dataset.serviceFields;
            const visible = group === type || (group === "paid" && type !== "animation");
            field.hidden = !visible;
            field.querySelectorAll("input, select").forEach((input) => {
                input.disabled = !visible;
                if (["expected_participants", "actual_participants", "invoice_reference", "client_name", "amount", "participants"].includes(input.name)) {
                    input.required = visible;
                }
            });
        });
        if (titleLabel) {
            titleLabel.textContent = type === "animation" ? "Titre de l'animation" : (
                type === "reservation" ? "Titre du créneau réservable" : "Nom de la machine"
            );
        }
        if (dateLabel) {
            dateLabel.textContent = type === "rental" ? "Date de prise de location" : "Date effectuée";
        }
    };
    typeSelect.addEventListener("change", updateFields);
    updateFields();
}

function configureCommuneSuggestions() {
    const postalCodeInput = document.querySelector("[data-postal-code]");
    const cityInput = document.querySelector("[data-city-input]");
    const suggestions = document.querySelector("[data-city-suggestions]");
    const status = document.querySelector("[data-city-suggestion-status]");
    if (!postalCodeInput || !cityInput || !suggestions || !status) return;

    const endpoint = postalCodeInput.dataset.communesUrl;
    if (!endpoint) return;
    let debounceTimer = null;
    let requestSequence = 0;
    let autoFilledCity = null;

    cityInput.addEventListener("input", () => {
        if (cityInput.value !== autoFilledCity) autoFilledCity = null;
    });

    const updateSuggestions = async () => {
        const postalCode = postalCodeInput.value.trim();
        const currentRequest = ++requestSequence;
        suggestions.replaceChildren();
        if (!/^\d{5}$/.test(postalCode)) {
            status.textContent = "Saisissez un code postal français à 5 chiffres pour obtenir les communes officielles.";
            return;
        }

        status.textContent = "Recherche des communes…";
        try {
            const separator = endpoint.includes("?") ? "&" : "?";
            const response = await fetch(
                `${endpoint}${separator}code_postal=${encodeURIComponent(postalCode)}`,
                { headers: { Accept: "application/json" } },
            );
            if (!response.ok) throw new Error("Référentiel indisponible");
            const payload = await response.json();
            if (currentRequest !== requestSequence) return;
            const communes = Array.isArray(payload.communes) ? payload.communes : [];
            communes.forEach((commune) => {
                const option = document.createElement("option");
                option.value = commune;
                suggestions.append(option);
            });
            if (communes.length === 1 && (!cityInput.value.trim() || cityInput.value === autoFilledCity)) {
                cityInput.value = communes[0];
                autoFilledCity = communes[0];
                status.textContent = `Commune renseignée automatiquement : ${communes[0]}.`;
            } else if (communes.length > 1) {
                status.textContent = `${communes.length} communes trouvées : choisissez la commune proposée dans le champ.`;
            } else if (payload.available === false) {
                status.textContent = "Le référentiel est temporairement indisponible ; la saisie manuelle reste possible.";
            } else {
                status.textContent = "Aucune commune française trouvée ; la saisie manuelle reste possible.";
            }
        } catch (_error) {
            if (currentRequest !== requestSequence) return;
            status.textContent = "Le référentiel est temporairement indisponible ; la saisie manuelle reste possible.";
        }
    };

    postalCodeInput.addEventListener("input", () => {
        window.clearTimeout(debounceTimer);
        debounceTimer = window.setTimeout(updateSuggestions, 250);
    });
    if (/^\d{5}$/.test(postalCodeInput.value.trim())) updateSuggestions();
}

function configureUserPhoneFields() {
    const countryCodeInput = document.querySelector("[data-phone-country-code]");
    const phoneInput = document.querySelector("[data-phone-number]");
    if (!countryCodeInput || !phoneInput) return;

    const normalizeCountryCode = () => {
        let value = countryCodeInput.value.replace(/\s+/g, "");
        if (value.startsWith("00")) value = `+${value.slice(2)}`;
        if (!value) value = "+33";
        countryCodeInput.value = value;
        return value;
    };
    const groupPairs = (digits) => {
        if (!digits) return "";
        const firstLength = digits.length % 2 === 0 ? 2 : 1;
        const groups = [digits.slice(0, firstLength)];
        for (let index = firstLength; index < digits.length; index += 2) {
            groups.push(digits.slice(index, index + 2));
        }
        return groups.join(" ");
    };
    const normalizePhone = () => {
        const countryCode = normalizeCountryCode();
        const prefixDigits = countryCode.replace(/\D/g, "");
        const rawValue = phoneInput.value.trim();
        let compactValue = rawValue.replace(/[().\-\s]/g, "");
        if (compactValue.startsWith(`+${prefixDigits}`)) {
            compactValue = compactValue.slice(prefixDigits.length + 1);
        } else if (compactValue.startsWith(`00${prefixDigits}`)) {
            compactValue = compactValue.slice(prefixDigits.length + 2);
        }
        let digits = compactValue.replace(/\D/g, "");
        if (countryCode === "+33" && digits.length === 9) digits = `0${digits}`;
        phoneInput.value = groupPairs(digits);
    };

    countryCodeInput.addEventListener("blur", normalizeCountryCode);
    phoneInput.addEventListener("blur", normalizePhone);
    phoneInput.form?.addEventListener("submit", normalizePhone);
}

function configureBillingForm() {
    const form = document.querySelector("[data-billing-form]");
    const total = document.querySelector("[data-billing-total]");
    if (!form || !total) return;

    const field = (name) => form.elements.namedItem(name);
    const billingType = () => field("billing_type")?.value || "reservation";
    const clientInput = form.querySelector("[data-billing-client-input]");
    const clientSuggestions = form.querySelector("[data-billing-client-suggestions]");
    const normalizeContact = (value) => (value || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLocaleLowerCase("fr-FR")
        .replace(/[^a-z0-9]+/g, " ")
        .trim();
    const numericValue = (name) => {
        const value = Number.parseInt(field(name)?.value || "0", 10);
        return Number.isFinite(value) && value > 0 ? value : 0;
    };
    const configuredCents = (name, fallback) => {
        const value = Number.parseInt(form.dataset[name] || `${fallback}`, 10);
        return Number.isFinite(value) && value >= 0 ? value : fallback;
    };
    const updateSections = () => {
        form.querySelectorAll("[data-billing-section]").forEach((section) => {
            section.hidden = section.dataset.billingSection !== billingType();
        });
        const isRental = billingType() === "rental";
        const dateLabel = form.querySelector("[data-billing-activity-date-label]");
        const startLabel = form.querySelector("[data-billing-start-time-label]");
        const endLabel = form.querySelector("[data-billing-end-time-label]");
        if (dateLabel) {
            dateLabel.textContent = isRental
                ? "Date du début de la location *"
                : "Date de début ou de l'activité *";
        }
        if (startLabel) {
            startLabel.textContent = isRental ? "Heure du rdv *" : "Heure de début *";
        }
        if (endLabel) {
            endLabel.textContent = isRental
                ? "Heure estimée de la fin du rdv *"
                : "Heure de fin *";
        }
    };
    const updateTotal = () => {
        if (billingType() === "rental") {
            const machine = field("rental_machine_key");
            const option = machine?.options[machine.selectedIndex];
            const monthlyCents = Number.parseInt(option?.dataset.monthlyCents || "0", 10);
            let amountCents = monthlyCents * numericValue("rental_months")
                + configuredCents("rentalContract", 2500);
            if (field("rental_delivery")?.checked) {
                amountCents += configuredCents("rentalDelivery", 3000);
            }
            total.textContent = new Intl.NumberFormat("fr-FR", {
                style: "currency",
                currency: "EUR",
            }).format(amountCents / 100);
            return;
        }
        const category = field("rate_category")?.value;
        const customSelect = field("custom_tariff_key");
        const customOption = customSelect?.selectedOptions[0];
        const unitField = field("rate_unit");
        if (customSelect?.value && customOption?.dataset.unit && unitField) {
            unitField.value = customOption.dataset.unit;
        }
        const unit = unitField?.value;
        const baseRates = category === "agglo"
            ? { hourly: 0, half_day: 0 }
            : category === "reduced"
                ? {
                    hourly: configuredCents("reducedHourly", 3000),
                    half_day: configuredCents("reducedHalfDay", 6000),
                }
                : {
                    hourly: configuredCents("normalHourly", 6000),
                    half_day: configuredCents("normalHalfDay", 12000),
                };
        const customCents = customSelect?.value ? Number.parseInt(customOption?.dataset.cents || "0", 10) : null;
        let amount = (customCents === null ? (baseRates[unit] || 0) : customCents) * numericValue("rate_quantity");
        amount += configuredCents("travelUnit", 6000) * numericValue("travel_quantity");
        if (field("consumable_mode")?.value === "billed") {
            amount += configuredCents("consumableUnit", 3000) * numericValue("consumable_quantity");
        }
        total.textContent = new Intl.NumberFormat("fr-FR", {
            style: "currency",
            currency: "EUR",
        }).format(amount / 100);
    };

    form.querySelectorAll("[data-billing-price]").forEach((element) => {
        element.addEventListener("input", updateTotal);
        element.addEventListener("change", updateTotal);
    });
    if (clientInput && clientSuggestions && clientInput.dataset.clientsUrl) {
        fetch(clientInput.dataset.clientsUrl, {
            cache: "no-store",
            headers: { Accept: "application/json" },
        })
            .then((response) => response.ok ? response.json() : Promise.reject())
            .then((payload) => {
                const clients = Array.isArray(payload.clients) ? payload.clients : [];
                const clientByName = new Map();
                clientSuggestions.replaceChildren();
                clients.forEach((client) => {
                    const key = normalizeContact(client.contact);
                    if (!key || clientByName.has(key)) return;
                    clientByName.set(key, client);
                    const option = document.createElement("option");
                    option.value = client.contact;
                    option.label = client.structure || "";
                    clientSuggestions.appendChild(option);
                });
                clientInput.addEventListener("change", () => {
                    const client = clientByName.get(normalizeContact(clientInput.value));
                    if (!client) return;
                    form.querySelectorAll("[data-billing-client-field]").forEach((input) => {
                        const property = input.dataset.billingClientField;
                        input.value = client[property] || "";
                    });
                    const postalCode = form.querySelector("[data-postal-code]");
                    postalCode?.dispatchEvent(new Event("input", { bubbles: true }));
                });
            })
            .catch(() => {
                // L'annuaire accélère la saisie mais ne bloque jamais le formulaire.
            });
    }
    field("billing_type")?.addEventListener("change", () => {
        updateSections();
        updateTotal();
    });
    updateSections();
    updateTotal();
}

function configureDemographicStatisticsFilters() {
    const root = document.querySelector("[data-statistics-filters]");
    const dataElement = document.getElementById("demographic-statistics-data");
    if (!root || !dataElement) return;

    let users;
    try {
        users = JSON.parse(dataElement.textContent || "[]");
    } catch (_error) {
        return;
    }
    if (!Array.isArray(users)) return;

    const options = Array.from(document.querySelectorAll("[data-stat-filter-option]"));
    const resetButton = root.querySelector("[data-statistics-reset]");
    const totalElement = root.querySelector("[data-statistics-filtered-total]");
    const totalLabel = totalElement?.nextElementSibling;
    const meanAgeElement = document.querySelector("[data-statistics-mean-age]");
    const dimensions = ["gender", "age_group", "city", "nationality"];

    const selectedValues = (dimension) => new Set(
        options
            .filter((option) => option.dataset.dimension === dimension)
            .filter((option) => option.querySelector("[data-stat-filter]")?.checked)
            .map((option) => option.dataset.key)
    );
    const selections = () => Object.fromEntries(
        dimensions.map((dimension) => [dimension, selectedValues(dimension)])
    );
    const userMatches = (user, activeSelections, ignoredDimension = null) => dimensions.every((dimension) => {
        if (dimension === ignoredDimension) return true;
        const selected = activeSelections[dimension];
        return selected.size === 0 || selected.has(String(user[dimension] ?? "unknown"));
    });
    const percentageLabel = (count, total) => {
        const percentage = total ? Math.round((count / total) * 1000) / 10 : 0;
        return `${count} · ${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(percentage)} %`;
    };

    const update = () => {
        const activeSelections = selections();
        const filteredUsers = users.filter((user) => userMatches(user, activeSelections));

        options.forEach((option) => {
            const dimension = option.dataset.dimension;
            const referenceUsers = users.filter((user) => userMatches(user, activeSelections, dimension));
            const count = referenceUsers.filter(
                (user) => String(user[dimension] ?? "unknown") === option.dataset.key
            ).length;
            const percentage = referenceUsers.length ? (count / referenceUsers.length) * 100 : 0;
            const checkbox = option.querySelector("[data-stat-filter]");
            const countElement = option.querySelector("[data-stat-count]");
            const bar = option.querySelector("[data-stat-bar]");
            option.classList.toggle("is-selected", Boolean(checkbox?.checked));
            option.classList.toggle("is-zero", count === 0);
            if (countElement) countElement.textContent = percentageLabel(count, referenceUsers.length);
            if (bar) bar.style.width = `${percentage}%`;
        });

        if (totalElement) totalElement.textContent = String(filteredUsers.length);
        if (totalLabel) {
            const plural = filteredUsers.length === 1 ? "" : "s";
            totalLabel.textContent = `usager${plural} affiché${plural}`;
        }
        if (meanAgeElement) {
            const ages = filteredUsers
                .map((user) => Number(user.age))
                .filter((age) => Number.isFinite(age) && age >= 0);
            meanAgeElement.textContent = ages.length
                ? `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(
                    ages.reduce((sum, age) => sum + age, 0) / ages.length
                )} ans`
                : "—";
        }
        if (resetButton) {
            resetButton.disabled = !dimensions.some(
                (dimension) => activeSelections[dimension].size > 0
            );
        }
    };

    options.forEach((option) => {
        option.querySelector("[data-stat-filter]")?.addEventListener("change", update);
    });
    resetButton?.addEventListener("click", () => {
        options.forEach((option) => {
            const checkbox = option.querySelector("[data-stat-filter]");
            if (checkbox) checkbox.checked = false;
        });
        update();
    });
    update();
}

function configureOpenLabAttendanceScale() {
    document.querySelectorAll("[data-openlab-attendance]").forEach((root) => {
        const scaleToggle = root.querySelector("[data-attendance-scale-toggle]");
        const visitorsToggle = root.querySelector("[data-attendance-visitors-toggle]");
        const status = root.querySelector("[data-attendance-scale-state]");
        if (!scaleToggle && !visitorsToggle) return;

        const update = () => {
            const usesWeeklyScale = scaleToggle?.checked ?? false;
            root.classList.toggle("uses-weekly-scale", usesWeeklyScale);
            root.classList.toggle(
                "includes-visitors",
                visitorsToggle ? visitorsToggle.checked : true
            );
            if (status) {
                status.textContent = usesWeeklyScale
                    ? "Échelle commune à tous les jours"
                    : "Échelle propre à chaque jour";
            }
        };

        scaleToggle?.addEventListener("change", update);
        visitorsToggle?.addEventListener("change", update);
        update();
    });
}

updateParisClock();
window.setInterval(updateParisClock, 1000);
enableUserSearch();
dismissFlashMessages();
registerApplicationMode();
configureScreenWakeLock();
displayWakeLockCompatibility();
configureIdentifierAutoSubmit();
configureQuickDeparture();
configureQrPreviews();
configureHomeLiveRefresh();
configureHomeScrollLock();
configureServiceForm();
configureCommuneSuggestions();
configureUserPhoneFields();
configureBillingForm();
configureDemographicStatisticsFilters();
configureOpenLabAttendanceScale();

function configureWalkinUserPrefill() {
    const form = document.querySelector("[data-walkin-prefill-url]");
    const select = form?.querySelector('select[name="public_id"]');
    if (!form || !select) return;
    const injected = new Map();
    let selection = 0;
    for (const name of ["first_name", "last_name", "birth_year", "email", "phone"]) {
        form.elements.namedItem(name)?.addEventListener("input", () => injected.delete(name));
    }
    select.addEventListener("change", async () => {
        const version = ++selection;
        const publicId = select.value;
        if (!publicId) {
            for (const [name, value] of injected) {
                const field = form.elements.namedItem(name);
                if (field && field.value === value) field.value = "";
            }
            injected.clear();
            return;
        }
        const before = new Map(["first_name", "last_name", "birth_year", "email", "phone"].map(name =>
            [name, form.elements.namedItem(name)?.value ?? ""]));
        try {
            const url = form.dataset.walkinPrefillUrl.replace("__PUBLIC_ID__", encodeURIComponent(publicId));
            const response = await fetch(url, { credentials: "same-origin", cache: "no-store" });
            if (!response.ok || selection !== version) return;
            const user = await response.json();
            if (selection !== version) return;
            for (const name of ["first_name", "last_name", "birth_year", "email", "phone"]) {
                const field = form.elements.namedItem(name);
                if (field && field.value === before.get(name)) {
                    field.value = user[name] ?? "";
                    injected.set(name, field.value);
                }
            }
        } catch (_error) {
            // La saisie manuelle reste disponible sans exposer de données au public.
        }
    });
}

configureWalkinUserPrefill();
