const areaForm = document.querySelector("#area-form");
const locationInput = document.querySelector("#location-input");
const quickButtons = document.querySelectorAll("[data-area]");
const demoFill = document.querySelector("#demo-fill");

const chatbot = document.querySelector("#chatbot");
const chatPanel = document.querySelector("#chat-panel");
const chatToggle = document.querySelector("#chat-toggle");
const chatClose = document.querySelector("#chat-close");
const chatForm = document.querySelector("#chat-form");
const chatInput = document.querySelector("#chat-input");
const messages = document.querySelector("#messages");

const facilityIcons = {
  convenience_store: `
    <svg viewBox="0 0 24 24">
      <path d="M4 10h16"></path>
      <path d="M5 10l1.2-5h11.6L19 10"></path>
      <path d="M6 10v10h12V10"></path>
      <path d="M9 20v-5h6v5"></path>
    </svg>
  `,
  supermarket: `
    <svg viewBox="0 0 24 24">
      <path d="M6 6h15l-1.5 8h-12z"></path>
      <path d="M6 6L5 3H2"></path>
      <circle cx="9" cy="20" r="1.5"></circle>
      <circle cx="18" cy="20" r="1.5"></circle>
    </svg>
  `,
  hospital: `
    <svg viewBox="0 0 24 24">
      <path d="M4 21V5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v16"></path>
      <path d="M9 21v-5h6v5"></path>
      <path d="M12 7v6"></path>
      <path d="M9 10h6"></path>
    </svg>
  `,
  clinic: `
    <svg viewBox="0 0 24 24">
      <path d="M12 21s7-4.6 7-10a7 7 0 0 0-14 0c0 5.4 7 10 7 10z"></path>
      <path d="M12 8v6"></path>
      <path d="M9 11h6"></path>
    </svg>
  `,
  pharmacy: `
    <svg viewBox="0 0 24 24">
      <path d="M10 21H7a4 4 0 0 1 0-8h3"></path>
      <path d="M14 3h3a4 4 0 0 1 0 8h-3"></path>
      <path d="M8 15l8-8"></path>
      <path d="M14 13h6v8h-6z"></path>
      <path d="M17 15v4"></path>
      <path d="M15 17h4"></path>
    </svg>
  `,
  park: `
    <svg viewBox="0 0 24 24">
      <path d="M12 3l4 7h-3l4 7h-4v4h-2v-4H7l4-7H8z"></path>
    </svg>
  `,
  bike_rental: `
    <svg viewBox="0 0 24 24">
      <circle cx="6" cy="17" r="3"></circle>
      <circle cx="18" cy="17" r="3"></circle>
      <path d="M8 17l4-7h3l3 7"></path>
      <path d="M12 10l-2-3"></path>
    </svg>
  `,
  mall: `
    <svg viewBox="0 0 24 24">
      <path d="M6 8h12l1 13H5z"></path>
      <path d="M9 8a3 3 0 0 1 6 0"></path>
    </svg>
  `,
  parking: `
    <svg viewBox="0 0 24 24">
      <path d="M7 21V3h6a5 5 0 0 1 0 10H7"></path>
    </svg>
  `,
};

const labels = {
  convenience_store: ["超商"],
  supermarket: ["超市"],
  hospital: ["醫院"],
  clinic: ["診所"],
  pharmacy: ["藥局"],
  park: ["公園"],
  bike_rental: ["自行車"],
  mall: ["商場"],
  parking: ["停車"],
};

function setText(selector, text) {
  document.querySelector(selector).textContent = text;
}

function sectionMessage(section, fallback) {
  if (!section) return fallback;
  return section.status === "success" ? section.message : section.message || fallback;
}

function mapsSearchUrl(query) {
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

function mapUrlForPlace(place, fallbackName = "") {
  if (!place) return "";
  if (place.google_maps_url) return place.google_maps_url;
  if (place.map_uri) return place.map_uri;
  if (place.latitude && place.longitude) return mapsSearchUrl(`${place.latitude},${place.longitude}`);
  if (fallbackName || place.name || place.restaurant_name) return mapsSearchUrl(fallbackName || place.name || place.restaurant_name);
  return "";
}

function createMapLink(url, label = "在地圖開啟") {
  const link = document.createElement("a");
  link.className = "map-link";
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = label;
  return link;
}

function compactSectionValue(section, type) {
  if (!section) return "查詢後顯示";
  if (section.status !== "success") return section.status === "pending" ? "待查詢" : "未完成";

  const data = section.data || {};
  if (type === "rent") {
    return data.rent_range_text || section.message;
  }
  if (type === "transport") {
    return data.transport_level ? `${data.transport_level} · ${data.score ?? 0} 分` : section.message;
  }
  if (type === "facility") {
    return data.facility_level ? `${data.facility_level} · ${data.score ?? 0} 分` : section.message;
  }
  return section.message;
}

function updateFacilityList(facility) {
  const facilityList = document.querySelector("#facility-list");
  facilityList.replaceChildren();

  if (!facility || facility.status !== "success") {
    [
    ["convenience_store", "超商 / 超市", "等待查詢"],
    ["hospital", "醫療 / 藥局", "等待查詢"],
    ["park", "公園 / 休閒", "等待查詢"]
    ].forEach(([iconKey, name, detail]) => {
    facilityList.appendChild(createFacility(iconKey, name, detail));
    });
    return;
  }

  const counts = facility.data.counts || {};
  const entries = Object.entries(labels)
    .filter(([key]) => counts[key])
    .slice(0, 5);

  if (!entries.length) {
    facilityList.appendChild(createFacility("查", "設施較少", "800 公尺內資料有限"));
    return;
  }
  entries.forEach(([key, [name]]) => {
    facilityList.appendChild(createFacility(key, name, `${counts[key]} 筆`));
  });


  const nearest = [];
  Object.entries(facility.data.nearest_facilities || {}).forEach(([key, places]) => {
    const label = labels[key]?.[1] || "設施";
    (places || []).slice(0, 2).forEach((place) => nearest.push({ ...place, categoryLabel: label }));
  });

  nearest
    .sort((a, b) => (a.distance_meters || 0) - (b.distance_meters || 0))
    .slice(0, 6)
    .forEach((place) => {
      const detail = `${place.categoryLabel} · 約 ${place.distance_meters ?? "-"} 公尺`;
      facilityList.appendChild(createFacility(key, place.name || "未命名設施", detail, mapUrlForPlace(place)));
    });
}

function createFacility(iconKey, name, detailText, mapUrl = "") {
  const item = document.createElement("div");
  item.className = "facility";

  const icon = document.createElement("b");
  icon.className = "facility-icon";

  if (facilityIcons[iconKey]) {
    icon.innerHTML = facilityIcons[iconKey];
  } else {
    icon.innerHTML = `
      <svg viewBox="0 0 24 24">
        <path d="M12 21s7-5.2 7-12a7 7 0 0 0-14 0c0 6.8 7 12 7 12z"></path>
        <circle cx="12" cy="9" r="2.4"></circle>
      </svg>
    `;
  }

  const label = document.createElement("span");
  label.textContent = name;

  const detail = document.createElement("small");
  detail.textContent = detailText;

  label.appendChild(detail);
  item.append(icon, label);

  if (mapUrl) {
    item.appendChild(createMapLink(mapUrl));
  }

  return item;
}

function updateTransportList(transport) {
  const transportList = document.querySelector("#transport-list");
  transportList.replaceChildren();

  if (!transport || transport.status !== "success") {
    const item = document.createElement("p");
    item.textContent = "查詢後會顯示附近捷運、台鐵或公車站點。";
    transportList.appendChild(item);
    return;
  }

  const items = [];
  const train = transport.data?.nearest_train_station;
  if (train) items.push({ ...train, label: "台鐵" });
  (transport.data?.nearby_mrt_stations || []).slice(0, 4).forEach((station) => {
    items.push({ ...station, label: station.system || "捷運" });
  });
  (transport.data?.nearby_bus_stops || []).slice(0, 4).forEach((stop) => {
    items.push({ ...stop, label: "公車" });
  });

  if (!items.length) {
    const item = document.createElement("p");
    item.textContent = transport.message || "附近暫未取得交通站點。";
    transportList.appendChild(item);
    return;
  }

  items.slice(0, 7).forEach((station) => {
    const row = document.createElement("div");
    row.className = "transport-link-row";
    const text = document.createElement("span");
    text.textContent = `${station.label} · ${station.name} · 約 ${station.distance_meters} 公尺`;
    row.appendChild(text);
    const url = mapUrlForPlace(station, `${station.label}${station.name}`);
    if (url) row.appendChild(createMapLink(url));
    transportList.appendChild(row);
  });
}

function appendTransportLinks(sections, extraList) {
  const transport = sections.transport;
  if (!transport || transport.status !== "success") return;

  const mrtStations = transport.data?.nearby_mrt_stations || [];
  if (!mrtStations.length) return;

  const group = document.createElement("div");
  group.className = "transport-links";
  const title = document.createElement("strong");
  title.textContent = "附近捷運站";
  group.appendChild(title);

  mrtStations.slice(0, 3).forEach((station) => {
    const row = document.createElement("div");
    row.className = "transport-link-row";
    const text = document.createElement("span");
    text.textContent = `${station.name} · 約 ${station.distance_meters} 公尺`;
    row.appendChild(text);
    row.appendChild(createMapLink(mapUrlForPlace(station, `${station.system || ""}${station.name}`)));
    group.appendChild(row);
  });

  extraList.appendChild(group);
}

function appendMealCards(section, extraList) {
  const recommendations = section.data?.recommendations || [];
  if (!recommendations.length) {
    const item = document.createElement("p");
    item.textContent = `${section.name}：${section.message}`;
    extraList.appendChild(item);
    return;
  }

  const wrap = document.createElement("div");
  wrap.className = "meal-card-list";

  recommendations.slice(0, 3).forEach((result, index) => {
    const restaurant = result.restaurant || {};
    const card = document.createElement("article");
    card.className = "meal-card";

    const head = document.createElement("div");
    head.className = "meal-card-head";
    const title = document.createElement("strong");
    title.textContent = `${index + 1}. ${restaurant.restaurant_name || "未命名餐廳"}`;
    const score = document.createElement("span");
    score.textContent = `分數 ${result.final_score ?? "-"}`;
    head.append(title, score);

    const meta = document.createElement("div");
    meta.className = "meal-meta";
    meta.textContent = `步行 ${restaurant.walk_time ?? "-"} 分鐘 · ${restaurant.distance_meters ?? "-"} 公尺`;

    const reason = document.createElement("p");
    reason.textContent = mealReason(result);

    const footer = document.createElement("div");
    footer.className = "meal-card-footer";
    const source = document.createElement("small");
    source.textContent = `資料來源：${restaurant.data_source || section.source || "Geoapify"}`;
    footer.appendChild(source);
    const url = mapUrlForPlace(restaurant);
    if (url) footer.appendChild(createMapLink(url));

    card.append(head, meta, reason, footer);
    wrap.appendChild(card);
  });

  extraList.appendChild(wrap);
}

function updateMealList(meal) {
  const mealList = document.querySelector("#meal-list");
  mealList.replaceChildren();

  if (!meal || meal.status === "pending") {
    const item = document.createElement("p");
    item.textContent = "勾選附近餐飲後會顯示推薦餐廳。";
    mealList.appendChild(item);
    return;
  }

  if (meal.status !== "success") {
    const item = document.createElement("p");
    item.textContent = meal.message || "餐飲推薦暫時無法取得。";
    mealList.appendChild(item);
    return;
  }

  appendMealCards(meal, mealList);
}

function mealReason(result) {
  const restaurant = result.restaurant || {};
  const scores = result.scores || {};
  if (scores.distance_score >= 0.9) {
    return "距離在可接受範圍內，適合租屋生活圈日常用餐。";
  }
  if (scores.preference_score >= 0.9) {
    return "符合這次輸入的飲食偏好。";
  }
  if (scores.health_score >= 0.8) {
    return "健康或蛋白質分數表現較好。";
  }
  if (restaurant.price === null || restaurant.price === undefined) {
    return "地圖資料未提供菜單價位，價格需再到店家頁面確認。";
  }
  return "在目前條件下整體分數較平衡。";
}

function updateExtraList(sections) {
  const extraList = document.querySelector("#extra-list");
  extraList.replaceChildren();
  const extras = [sections.air, sections.night].filter((section) => section && section.status !== "pending");

  if (!extras.length) {
    const item = document.createElement("p");
    item.textContent = "勾選空氣品質或夜間生活後會顯示結果。";
    extraList.appendChild(item);
    return;
  }

  extras.forEach((section) => {
    const item = document.createElement("p");
    item.textContent = `${section.name}：${section.message}`;
    extraList.appendChild(item);
  });
}

function updateSources(sources) {
  const sourceList = document.querySelector("#source-list");
  sourceList.replaceChildren();

  sources.forEach((source) => {
    const item = document.createElement("div");
    item.className = source.status === "success" ? "success" : "error";
    const state = source.status === "success" ? "完成" : source.status === "pending" ? "待查詢" : "未完成";
    item.innerHTML = `<b>${source.name || "資料源"} · ${state}</b><br>${source.source || "Housing Agent"}<br>${source.message || ""}`;
    sourceList.appendChild(item);
  });
}

function updateAreaCard(data) {
  const sections = data.sections || {};
  const location = data.location?.data || {};

  setText("#area-title", data.area || "指定區域");
  setText("#area-district", location.display_name || "地點解析完成");
  setText("#analysis-status", data.ok ? "Done" : "Check");
  setText("#report-time", `${data.generated_at} 更新`);
  setText("#rent-value", compactSectionValue(sections.rent, "rent"));
  setText("#traffic-value", compactSectionValue(sections.transport, "transport"));
  setText("#facility-value", compactSectionValue(sections.facility, "facility"));
  setText("#area-summary", data.summary || "查詢完成。");

  updateFacilityList(sections.facility);
  updateTransportList(sections.transport);
  updateMealList(sections.meal);
  updateExtraList(sections);
  updateSources(data.sources || []);
}

async function analyzeArea(location) {
  const submitButton = areaForm.querySelector("button");
  const originalLabel = submitButton.innerHTML;
  submitButton.disabled = true;
  submitButton.textContent = "Agent 分析中...";

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        location,
        include_air: true,
        include_night: true,
        include_meal: true,
      }),
    });
    const result = await response.json();
    if (!response.ok && !result.summary) throw new Error(result.error || "分析失敗");
    updateAreaCard(result);
  } catch (error) {
    addMessage(error.message || "暫時無法整理區域資料，請稍後再試。", "bot");
    openChat();
  } finally {
    submitButton.disabled = false;
    submitButton.innerHTML = originalLabel;
  }
}

areaForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const location = locationInput.value.trim();
  if (location) analyzeArea(location);
});

quickButtons.forEach((button) => {
  button.addEventListener("click", () => {
    locationInput.value = button.dataset.area;
    analyzeArea(button.dataset.area);
  });
});

demoFill.addEventListener("click", () => {
  locationInput.value = "中央大學附近";
  analyzeArea(locationInput.value);
});

function openChat() {
  chatbot.classList.add("open");
  chatPanel.setAttribute("aria-hidden", "false");
  chatToggle.setAttribute("aria-expanded", "true");
  chatInput.focus();
}

function closeChat() {
  chatbot.classList.remove("open");
  chatPanel.setAttribute("aria-hidden", "true");
  chatToggle.setAttribute("aria-expanded", "false");
}

function addMessage(text, role) {
  const bubble = document.createElement("div");
  bubble.className = `message ${role}`;
  bubble.textContent = text;
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
}

async function askAssistant(message) {
  addMessage(message, "user");
  chatInput.value = "";
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const result = await response.json();
    addMessage(result.reply || result.error || "我暫時沒有取得回覆。", "bot");
  } catch (error) {
    addMessage("目前連線不穩定，請稍後再問我一次。", "bot");
  }
}

chatToggle.addEventListener("click", openChat);
chatClose.addEventListener("click", closeChat);
chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = chatInput.value.trim();
  if (message) askAssistant(message);
});

document.querySelectorAll(".chat-suggestions button").forEach((button) => {
  button.addEventListener("click", () => askAssistant(button.textContent));
});
