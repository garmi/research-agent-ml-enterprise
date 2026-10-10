// Interactive enhancements: Theme toggler, tag filter chips, and smooth citation jumps
document.addEventListener("DOMContentLoaded", () => {
  // Theme toggle
  const themeBtn = document.getElementById("theme-toggle");
  if (themeBtn) {
    const currentTheme = localStorage.getItem("theme") || 
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", currentTheme);

    themeBtn.addEventListener("click", () => {
      const active = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", active);
      localStorage.setItem("theme", active);
    });
  }

  // Tag filter chips on insights directory
  const chips = document.querySelectorAll(".filter-chip");
  const cards = document.querySelectorAll(".insight-card-item");

  if (chips.length && cards.length) {
    chips.forEach(chip => {
      chip.addEventListener("click", () => {
        chips.forEach(c => c.classList.remove("active"));
        chip.classList.add("active");
        const tag = chip.getAttribute("data-tag");

        cards.forEach(card => {
          if (tag === "all" || card.getAttribute("data-tags")?.includes(tag)) {
            card.style.display = "block";
          } else {
            card.style.display = "none";
          }
        });
      });
    });
  }
});
