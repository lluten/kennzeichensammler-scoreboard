function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatPercent(value) {
  return `${Math.round(value * 100)}%`;
}

function formatDate(value) {
  const date = new Date(value);
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

function renderLandBreakdown(profile) {
  const target = document.getElementById("land-breakdown");
  if (!target) {
    return;
  }
  if (!profile.landBreakdown.length) {
    target.append(emptyState("No land breakdown available."));
    return;
  }

  profile.landBreakdown.forEach((item) => {
    const wrapper = createEl("div", "bar-item");
    const header = createEl("div", "bar-item-header");
    header.append(
      createEl("span", "", item.land),
      createEl("span", "", `${formatNumber(item.count)} (${formatPercent(item.share)})`)
    );
    const track = createEl("div", "bar-track");
    const fill = createEl("div", "bar-fill");
    fill.style.width = `${Math.max(item.share * 100, 3)}%`;
    track.append(fill);
    wrapper.append(header, track);
    target.append(wrapper);
  });
}

function renderHighlights(profile) {
  const target = document.getElementById("profile-highlights");
  if (!target) {
    return;
  }

  const cards = [
    {
      title: "efficiency",
      value: formatPercent(profile.stats.discoveryEfficiency),
      context: "unique IDs divided by total sightings",
      winner: `repeat rate: ${formatPercent(profile.stats.repeatRate)}`,
    },
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

function renderDailyBreakdown(profile) {
  const target = document.getElementById("daily-breakdown");
  if (!target) {
    return;
  }
  const series = profile.series.dailyActivity;
  if (!series.length) {
    target.append(emptyState("No daily data available."));
    return;
  }

  const maxTotal = Math.max(...series.map((day) => day.totalSightings));
  series.forEach((day) => {
    const row = createEl("div", "daily-row");
    const header = createEl("div", "daily-row-header");
    header.append(
      createEl("span", "", day.label),
      createEl("span", "", `${day.newDiscoveries} new / ${day.repeatSightings} repeat`)
    );

    const bar = createEl("div", "daily-bar");
    const newPart = createEl("div", "daily-bar-new");
    const repeatPart = createEl("div", "daily-bar-repeat");
    const emptyPart = createEl("div", "daily-bar-empty");
    newPart.style.width = `${(day.newDiscoveries / maxTotal) * 100}%`;
    repeatPart.style.width = `${(day.repeatSightings / maxTotal) * 100}%`;
    emptyPart.style.width = `${((maxTotal - day.totalSightings) / maxTotal) * 100}%`;

    bar.append(newPart, repeatPart, emptyPart);
    row.append(header, bar);
    target.append(row);
  });
}

function buildLinePath(points) {
  return points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
}

function renderActivityChart(profile) {
  const target = document.getElementById("activity-chart");
  if (!target) {
    return;
  }
  const series = profile.series.dailyActivity;
  if (!series.length) {
    target.append(emptyState("No activity series available."));
    return;
  }

  const width = 760;
  const height = 280;
  const padding = { top: 24, right: 24, bottom: 42, left: 44 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const maxSightings = Math.max(...series.map((day) => day.cumulativeSightings));
  const maxUnique = Math.max(...series.map((day) => day.cumulativeUniqueKennids));

  const xForIndex = (index) => {
    if (series.length === 1) {
      return padding.left + chartWidth / 2;
    }
    return padding.left + (index / (series.length - 1)) * chartWidth;
  };
  const yForValue = (value, maxValue) => {
    if (maxValue === 0) {
      return padding.top + chartHeight;
    }
    return padding.top + chartHeight - (value / maxValue) * chartHeight;
  };

  const sightingPoints = series.map((day, index) => ({
    x: xForIndex(index),
    y: yForValue(day.cumulativeSightings, maxSightings),
  }));
  const uniquePoints = series.map((day, index) => ({
    x: xForIndex(index),
    y: yForValue(day.cumulativeUniqueKennids, maxUnique),
  }));

  const fillPath = `${buildLinePath(sightingPoints)} L ${sightingPoints[sightingPoints.length - 1].x.toFixed(2)} ${(padding.top + chartHeight).toFixed(2)} L ${sightingPoints[0].x.toFixed(2)} ${(padding.top + chartHeight).toFixed(2)} Z`;

  const lastSightings = sightingPoints[sightingPoints.length - 1];
  const lastUnique = uniquePoints[uniquePoints.length - 1];
  const xLabels = [series[0].label, series[series.length - 1].label];

  target.innerHTML = `
    <svg class="svg-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Cumulative activity chart">
      <path class="chart-fill" d="${fillPath}"></path>
      <line class="chart-axis" x1="${padding.left}" y1="${padding.top + chartHeight}" x2="${padding.left + chartWidth}" y2="${padding.top + chartHeight}"></line>
      <line class="chart-axis" x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${padding.top + chartHeight}"></line>
      <path class="chart-line" d="${buildLinePath(sightingPoints)}"></path>
      <path class="chart-line-secondary" d="${buildLinePath(uniquePoints)}"></path>
      <text class="chart-value" x="${lastSightings.x - 6}" y="${lastSightings.y - 10}" text-anchor="end">${formatNumber(series[series.length - 1].cumulativeSightings)} total</text>
      <text class="chart-value" x="${lastUnique.x - 6}" y="${lastUnique.y - 10}" text-anchor="end">${formatNumber(series[series.length - 1].cumulativeUniqueKennids)} unique</text>
      <text class="chart-label" x="${padding.left}" y="${height - 12}">${xLabels[0]}</text>
      <text class="chart-label" x="${padding.left + chartWidth}" y="${height - 12}" text-anchor="end">${xLabels[1]}</text>
    </svg>
  `;
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
  renderActivityChart(profile);
  renderDailyBreakdown(profile);
  renderLandBreakdown(profile);
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
