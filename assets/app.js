function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatPercent(value) {
  return `${Math.round(value * 100)}%`;
}

function formatDate(value) {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

function lowerName(name) {
  return name.toLowerCase();
}

function createEl(tag, className, textContent) {
  const element = document.createElement(tag);
  if (className) {
    element.className = className;
  }
  if (textContent !== undefined) {
    element.textContent = textContent;
  }
  return element;
}

function emptyState(message) {
  const wrapper = createEl("div", "empty-state");
  wrapper.textContent = message;
  return wrapper;
}

function renderLeaderboard(manifest) {
  const leaderboard = document.getElementById("leaderboard");
  const awardsList = document.getElementById("awards-list");
  const meta = document.getElementById("leaderboard-meta");
  if (!leaderboard || !awardsList || !meta) {
    return;
  }

  meta.append(
    createEl("span", "meta-chip", `${manifest.friendCount} collector${manifest.friendCount === 1 ? "" : "s"}`),
    createEl("span", "meta-chip", `updated ${manifest.generatedAt.slice(0, 10)}`)
  );

  if (!manifest.leaderboard.length) {
    leaderboard.append(emptyState("No collector backups were found."));
    return;
  }

  manifest.leaderboard.forEach((entry) => {
    const row = createEl("a", "row");
    row.href = entry.profilePath;

    const primary = createEl("div", "primary-info");
    primary.append(
      createEl("span", "rank", String(entry.rank)),
      createEl("span", "name", lowerName(entry.displayName)),
      createEl("span", "score", `${formatNumber(entry.stats.uniqueKennids)} unique`)
    );

    const hover = createEl("div", "hover-info");
    entry.hoverInfo.forEach((line) => hover.append(createEl("span", "", line)));

    row.append(primary, hover);
    leaderboard.append(row);
  });

  manifest.awards.forEach((award) => {
    const card = createEl("div", "stat-card award-card");
    card.append(
      createEl("h3", "", award.title),
      createEl("p", "stat-value", award.value),
      createEl("p", "award-context", award.context),
      createEl("p", "award-winner", `held by: ${lowerName(award.winner)}`)
    );
    awardsList.append(card);
  });
}

function renderStatsGrid(profile) {
  const target = document.getElementById("profile-stats");
  if (!target) {
    return;
  }

  const cards = [
    {
      title: "unique IDs",
      value: formatNumber(profile.stats.uniqueKennids),
      context: "distinct Kennzeichen IDs discovered",
    },
    {
      title: "total sightings",
      value: formatNumber(profile.stats.totalSightings),
      context: "all rows from the latest backup",
    },
    {
      title: "active days",
      value: formatNumber(profile.stats.activeDays),
      context: `last activity ${formatDate(profile.stats.lastSeenDate)}`,
    },
    {
      title: "longest streak",
      value: `${formatNumber(profile.stats.longestStreakDays)} days`,
      context: "consecutive days with at least one sighting",
    },
    {
      title: "Germany",
      value: formatNumber(profile.stats.germanyUnique),
      context: "unique districts collected",
    },
    {
      title: "Europe",
      value: formatNumber(profile.stats.europeUnique),
      context: "unique countries / plates collected",
    },
    {
      title: "USA",
      value: formatNumber(profile.stats.usaUnique),
      context: "unique US plates collected",
    },
    {
      title: "efficiency",
      value: formatPercent(profile.stats.discoveryEfficiency),
      context: `repeat rate ${formatPercent(profile.stats.repeatRate)}`,
    },
  ];

  cards.forEach((cardData) => {
    const card = createEl("div", "stat-card");
    card.append(
      createEl("h3", "", cardData.title),
      createEl("p", "stat-value", cardData.value),
      createEl("p", "stat-context", cardData.context)
    );
    target.append(card);
  });
}

function renderHighlights(profile) {
  const target = document.getElementById("profile-highlights");
  if (!target) {
    return;
  }

  const cards = [
    {
      title: "consistency",
      value: formatPercent(profile.stats.activityConsistency),
      context: "share of active days within the recorded span",
      winner: `span: ${formatNumber(profile.stats.spanDays)} days`,
    },
    {
      title: "best day",
      value: `${formatNumber(profile.stats.bestDayBySightings.totalSightings)} logs`,
      context: profile.stats.bestDayBySightings.label,
      winner: `${formatNumber(profile.stats.bestDayByUniqueDiscoveries.newDiscoveries)} new IDs on top day`,
    },
    {
      title: "avg / active day",
      value: formatNumber(profile.stats.averageSightingsPerActiveDay),
      context: "mean sightings on days with activity",
      winner: `${formatNumber(profile.stats.repeatSightings)} repeats overall`,
    },
  ];

  cards.forEach((cardData) => {
    const card = createEl("div", "stat-card award-card highlight-card");
    card.append(
      createEl("h3", "", cardData.title),
      createEl("p", "stat-value", cardData.value),
      createEl("p", "award-context", cardData.context),
      createEl("p", "award-winner", cardData.winner)
    );
    target.append(card);
  });
}

function renderActivityHeatmap(profile) {
  const target = document.getElementById("activity-chart");
  if (!target) {
    return;
  }

  const days = profile.series.calendarHeatmap || [];
  if (!days.length) {
    target.append(emptyState("No activity series available."));
    return;
  }

  const weeks = [];
  for (let index = 0; index < days.length; index += 7) {
    weeks.push(days.slice(index, index + 7));
  }

  const monthLabels = [];
  let lastMonthKey = "";
  weeks.forEach((week, weekIndex) => {
    const firstDay = week.find(Boolean);
    if (!firstDay) {
      return;
    }
    const date = new Date(`${firstDay.date}T00:00:00`);
    const monthKey = `${date.getFullYear()}-${date.getMonth()}`;
    if (monthKey !== lastMonthKey) {
      monthLabels.push({
        weekIndex,
        label: date.toLocaleString("en", { month: "short" }),
      });
      lastMonthKey = monthKey;
    }
  });

  const root = createEl("div", "heatmap");
  const months = createEl("div", "heatmap-months");
  months.style.gridTemplateColumns = `repeat(${weeks.length}, minmax(0, 1fr))`;
  weeks.forEach((_, weekIndex) => {
    const label = monthLabels.find((entry) => entry.weekIndex === weekIndex);
    months.append(createEl("span", "heatmap-month", label ? label.label : ""));
  });

  const body = createEl("div", "heatmap-body");
  const weekdayLabels = createEl("div", "heatmap-weekdays");
  ["", "Mon", "", "Wed", "", "Fri", ""].forEach((label) => {
    weekdayLabels.append(createEl("span", "", label));
  });

  const grid = createEl("div", "heatmap-grid");
  grid.style.gridTemplateColumns = `repeat(${weeks.length}, minmax(0, 1fr))`;

  weeks.forEach((week) => {
    const column = createEl("div", "heatmap-week");
    for (let dayIndex = 0; dayIndex < 7; dayIndex += 1) {
      const day = week[dayIndex];
      const cell = createEl("div", "heatmap-day");
      if (!day) {
        cell.classList.add("is-empty");
        column.append(cell);
        continue;
      }
      cell.dataset.level = String(day.level);
      cell.title = `${day.label}: ${day.count} sighting${day.count === 1 ? "" : "s"}`;
      column.append(cell);
    }
    grid.append(column);
  });

  body.append(weekdayLabels, grid);

  const legend = createEl("div", "heatmap-legend");
  legend.append(createEl("span", "", "Less"));
  for (let level = 0; level <= 4; level += 1) {
    const swatch = createEl("span", "heatmap-day");
    swatch.dataset.level = String(level);
    legend.append(swatch);
  }
  legend.append(createEl("span", "", "More"));

  root.append(months, body, legend);
  target.replaceChildren(root);
}

function renderRegionProgress(profile) {
  const tabs = document.getElementById("region-tabs");
  const panel = document.getElementById("region-panel");
  if (!tabs || !panel) {
    return;
  }

  const categories = ["germany", "europe", "usa"]
    .map((id) => profile.regionCategories?.[id])
    .filter(Boolean);

  if (!categories.length) {
    panel.append(emptyState("No region data available."));
    return;
  }

  const defaultId =
    categories.find((category) => category.uniqueCount > 0)?.id || categories[0].id;

  function paint(activeId) {
    tabs.replaceChildren();
    panel.replaceChildren();

    categories.forEach((category) => {
      const completion = category.catalogTotal
        ? `${formatNumber(category.uniqueCount)}/${formatNumber(category.catalogTotal)}`
        : formatNumber(category.uniqueCount);
      const button = createEl("button", "region-tab", `${category.label} (${completion})`);
      button.type = "button";
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", category.id === activeId ? "true" : "false");
      if (category.id === activeId) {
        button.classList.add("is-active");
      }
      button.addEventListener("click", () => paint(category.id));
      tabs.append(button);
    });

    const active = categories.find((category) => category.id === activeId) || categories[0];
    const summary = createEl("div", "region-summary");
    const completionText =
      active.catalogTotal != null
        ? `${formatNumber(active.uniqueCount)} of ${formatNumber(active.catalogTotal)} catalog regions`
        : `${formatNumber(active.uniqueCount)} unique regions`;
    summary.append(
      createEl(
        "p",
        "",
        `${completionText} · ${formatNumber(active.totalSightings)} sightings${
          active.completion != null ? ` · ${formatPercent(active.completion)} complete` : ""
        }`
      )
    );
    panel.append(summary);

    if (!active.items.length) {
      panel.append(emptyState(`No ${active.label} entries in this backup yet.`));
      return;
    }

    const list = createEl("div", "bar-list region-bar-list");
    const maxCount = Math.max(1, ...active.items.map((item) => item.count));
    active.items.forEach((item) => {
      const wrapper = createEl("div", "bar-item");
      if (!item.collected && item.count === 0) {
        wrapper.classList.add("is-missing");
      }
      const header = createEl("div", "bar-item-header");
      const title = createEl("span", "region-code", item.label || item.code || String(item.kennid));
      const metaParts = [];
      if (item.region) {
        metaParts.push(item.region);
      }
      if (item.count > 0) {
        metaParts.push(`${formatNumber(item.count)}×`);
        if (item.firstSeenDate) {
          metaParts.push(`first ${formatDate(item.firstSeenDate)}`);
        }
      } else {
        metaParts.push("not collected");
      }
      header.append(title, createEl("span", "", metaParts.join(" · ")));
      const track = createEl("div", "bar-track");
      const fill = createEl("div", "bar-fill");
      const width = item.count > 0 ? Math.max((item.count / maxCount) * 100, 8) : 0;
      fill.style.width = `${width}%`;
      track.append(fill);
      wrapper.append(header, track);
      list.append(wrapper);
    });
    panel.append(list);
  }

  paint(defaultId);
}

async function loadJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}`);
  }
  return response.json();
}

async function initLeaderboard() {
  const manifest = await loadJson("data/manifest.json");
  renderLeaderboard(manifest);
}

async function initProfile() {
  const friendId = document.body.dataset.friendId;
  const profile = await loadJson(`../data/friends/${friendId}.json`);

  const title = document.getElementById("profile-title");
  const intro = document.getElementById("profile-intro");
  if (title) {
    title.textContent = `${lowerName(profile.displayName)}'s statistics`;
  }
  if (intro) {
    intro.textContent = `Latest backup: ${profile.sourceBackup}. Data window ${formatDate(profile.stats.firstSeenDate)} to ${formatDate(profile.stats.lastSeenDate)}.`;
  }

  renderStatsGrid(profile);
  renderActivityHeatmap(profile);
  renderRegionProgress(profile);
  renderHighlights(profile);
}

async function main() {
  try {
    if (document.body.dataset.page === "leaderboard") {
      await initLeaderboard();
    } else if (document.body.dataset.page === "profile") {
      await initProfile();
    }
  } catch (error) {
    const container = document.querySelector(".container");
    if (container) {
      container.append(emptyState(error.message));
    }
    console.error(error);
  }
}

main();
