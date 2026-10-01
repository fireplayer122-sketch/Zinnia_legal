document.addEventListener("DOMContentLoaded", () => {
    const navToggle = document.querySelector(".mobile-nav-toggle");
    const navLinks = document.querySelector(".nav-links");

    if (navToggle && navLinks) {
        navToggle.addEventListener("click", () => {
            const isOpen = navLinks.classList.toggle("open");
            navToggle.setAttribute("aria-expanded", String(isOpen));
        });
    }

    loadStats();
    setupCollectionSearch();
    setupWheel();
});


async function loadStats() {
    const targets = document.querySelectorAll("[data-stat]");

    if (!targets.length) return;

    try {
        const response = await fetch("/api/stats");

        if (!response.ok) {
            throw new Error("Stats request failed");
        }

        const stats = await response.json();

        for (const element of targets) {
            const key = element.dataset.stat;
            animateNumber(
                element,
                Number(stats[key] || 0)
            );
        }
    } catch (error) {
        for (const element of targets) {
            element.textContent = "—";
        }
    }
}


function animateNumber(element, target) {
    const duration = 900;
    const start = performance.now();

    function frame(now) {
        const progress = Math.min(
            1,
            (now - start) / duration
        );

        const eased = 1 - Math.pow(
            1 - progress,
            3
        );

        element.textContent = Math.round(
            target * eased
        ).toLocaleString();

        if (progress < 1) {
            requestAnimationFrame(frame);
        }
    }

    requestAnimationFrame(frame);
}


function setupCollectionSearch() {
    const search = document.querySelector("#collectionSearch");
    const cards = [
        ...document.querySelectorAll(".collection-card")
    ];

    if (!search || !cards.length) return;

    search.addEventListener("input", () => {
        const query = search.value.trim().toLowerCase();

        for (const card of cards) {
            const haystack = card.dataset.search || "";

            card.hidden = Boolean(
                query
                && !haystack.includes(query)
            );
        }
    });
}


function setupWheel() {
    const button = document.querySelector("#spinWheelButton");
    const wheel = document.querySelector("#zinniaWheel");
    const result = document.querySelector("#wheelResult");

    if (!button || !wheel || !result) return;

    const rewards = [
        "Zens",
        "Ashes",
        "XP",
        "Dandelion",
        "Extra Grab",
        "Extra Drop"
    ];

    let turns = 0;

    button.addEventListener("click", () => {
        button.disabled = true;

        const rewardIndex = Math.floor(
            Math.random() * rewards.length
        );

        turns += 5 + Math.random() * 2;

        const offset = rewardIndex * 60 + 30;
        const degrees = turns * 360 + (360 - offset);

        wheel.style.transform = `rotate(${degrees}deg)`;
        result.textContent = "Spinning...";

        window.setTimeout(() => {
            result.textContent =
                `Preview landed on: ${rewards[rewardIndex]}`;

            button.disabled = false;
        }, 4000);
    });
}
