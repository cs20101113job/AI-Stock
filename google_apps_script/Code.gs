var SHEET_HEADERS = [
  "股號",
  "股名",
  "類股",
  "種類",
  "交易狀態",
  "預計買股金額",
  "預計買股數量",
  "預計買股花費金額",
  "實際買股日期",
  "實際買股金額",
  "實際買股數量",
  "實際買股花費金額",
  "買股手續費",
  "預計賣股金額",
  "預計賣股數量",
  "預計賣股所得金額",
  "實際賣股日期",
  "實際賣股金額",
  "實際賣股數量",
  "實際賣股所得金額",
  "賣股手續費",
  "英文股名",
  "當天收盤價／現價"
];

var SHEET_NAME = "股票買買";
var MONITOR_TIME_ZONE = "Asia/Taipei";
var MONITOR_TRIGGER_FUNCTION = "monitorStockPrices";
var MONITOR_MAX_ALERTS_PER_CONDITION = 5;
var HOLIDAY_API_URL = "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule";
var QUOTE_API_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp";

function getSheet_() {
  var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = spreadsheet.getSheetByName(SHEET_NAME);
  if (!sheet) {
    var availableNames = spreadsheet.getSheets().map(function (item) {
      return item.getName();
    });
    throw new Error(
      '找不到工作表「' + SHEET_NAME + '」。目前工作表：' + availableNames.join("、")
    );
  }
  return sheet;
}

function ensureHeaders_(sheet) {
  if (sheet.getLastRow() === 0) {
    sheet.getRange(1, 1, 1, SHEET_HEADERS.length).setValues([SHEET_HEADERS]);
    sheet.setFrozenRows(1);
    return;
  }

  var lastColumn = Math.max(sheet.getLastColumn(), 1);
  var firstRow = sheet.getRange(1, 1, 1, lastColumn).getDisplayValues()[0]
    .map(function (value) { return String(value).trim(); });
  var headerIndexes = {};
  firstRow.forEach(function (header, index) {
    if (SHEET_HEADERS.indexOf(header) !== -1) {
      headerIndexes[header] = index;
    }
  });
  var hasHeaders = Object.keys(headerIndexes).length > 0;

  if (!hasHeaders) {
    sheet.insertRowBefore(1);
    var lastRow = sheet.getLastRow();
    var oldRows = lastRow > 1
      ? sheet.getRange(2, 1, lastRow - 1, lastColumn).getValues()
      : [];
    var migratedRows = oldRows.map(function (row) {
      var mapped = SHEET_HEADERS.map(function (_, index) {
        return row[index] === undefined ? "" : row[index];
      });
      return mapped;
    });
    sheet.getRange(1, 1, 1, SHEET_HEADERS.length).setValues([SHEET_HEADERS]);
    if (migratedRows.length) {
      sheet.getRange(2, 1, migratedRows.length, SHEET_HEADERS.length).setValues(migratedRows);
    }
    sheet.setFrozenRows(1);
    return;
  }

  var lastRowWithHeaders = sheet.getLastRow();
  var existingRows = lastRowWithHeaders > 1
    ? sheet.getRange(2, 1, lastRowWithHeaders - 1, lastColumn).getValues()
    : [];
  var unknownHeaders = firstRow.filter(function (header) {
    return header && SHEET_HEADERS.indexOf(header) === -1;
  });
  var normalizedHeaders = SHEET_HEADERS.concat(unknownHeaders);
  var normalizedRows = existingRows.map(function (row) {
    var mapped = SHEET_HEADERS.map(function (header) {
      var index = headerIndexes[header];
      return index === undefined || row[index] === undefined ? "" : row[index];
    });
    unknownHeaders.forEach(function (header) {
      var index = firstRow.indexOf(header);
      mapped.push(index === -1 || row[index] === undefined ? "" : row[index]);
    });
    return mapped;
  });

  sheet.getRange(1, 1, 1, normalizedHeaders.length).setValues([normalizedHeaders]);
  if (normalizedRows.length) {
    sheet.getRange(2, 1, normalizedRows.length, normalizedHeaders.length).setValues(normalizedRows);
  }
  sheet.setFrozenRows(1);
}

function jsonOutput_(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

function doGet() {
  var sheet = getSheet_();
  ensureHeaders_(sheet);

  var data = sheet.getDataRange().getValues();
  var result = [];

  for (var i = 1; i < data.length; i++) {
    var row = data[i];
    if (row.every(function (value) { return value === "" || value === null; })) {
      continue;
    }

    var record = {};
    SHEET_HEADERS.forEach(function (header, index) {
      record[header] = row[index] === undefined ? "" : row[index];
    });
    record._sheet_row = i + 1;
    result.push(record);
  }

  return jsonOutput_(result);
}

function doPost(e) {
  try {
    var sheet = getSheet_();
    ensureHeaders_(sheet);

    var contents = JSON.parse(e.postData.contents);
    if (!contents || !contents.row) {
      throw new Error("Request body must contain row data.");
    }

    var rowData;
    if (Array.isArray(contents.row)) {
      var sourceHeaders = Array.isArray(contents.headers)
        ? contents.headers
        : SHEET_HEADERS;
      var rowByHeader = {};
      sourceHeaders.forEach(function (header, index) {
        rowByHeader[header] = contents.row[index];
      });
      rowData = SHEET_HEADERS.map(function (header) {
        return rowByHeader[header] === undefined ? "" : rowByHeader[header];
      });
    } else if (typeof contents.row === "object") {
      rowData = SHEET_HEADERS.map(function (header) {
        return contents.row[header] === undefined ? "" : contents.row[header];
      });
    } else {
      throw new Error("row must be an array or object.");
    }

    if (contents.action === "update") {
      var rowNumber = Number(contents.rowNumber);
      if (!Number.isInteger(rowNumber) || rowNumber < 2 || rowNumber > sheet.getLastRow()) {
        throw new Error("Invalid row number for updating a trade.");
      }
      var stockIdColumn = SHEET_HEADERS.indexOf("股號") + 1;
      var existingStockId = String(
        sheet.getRange(rowNumber, stockIdColumn).getDisplayValue()
      ).trim().replace(/\.0$/, "");
      var expectedStockId = String(contents.expectedStockId || "").trim().replace(/\.0$/, "");
      if (!expectedStockId || existingStockId !== expectedStockId) {
        throw new Error("The selected trade changed in Google Sheet. Reload before updating.");
      }
      var statusColumn = SHEET_HEADERS.indexOf("交易狀態") + 1;
      var existingStatus = String(
        sheet.getRange(rowNumber, statusColumn).getDisplayValue()
      ).trim();
      if (contents.expectedStatus && existingStatus !== contents.expectedStatus) {
        throw new Error("The selected trade status changed in Google Sheet. Reload before updating.");
      }
      sheet.getRange(rowNumber, 1, 1, SHEET_HEADERS.length).setValues([rowData]);
    } else {
      sheet.appendRow(rowData);
    }

    return jsonOutput_({ result: "success" });
  } catch (error) {
    return jsonOutput_({ result: "error", message: error.toString() });
  }
}

function installPriceMonitor() {
  var properties = PropertiesService.getScriptProperties();
  if (!properties.getProperty("TELEGRAM_BOT_TOKEN") ||
      !properties.getProperty("TELEGRAM_CHAT_ID")) {
    throw new Error(
      "請先在 Apps Script 指令碼屬性設定 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID。"
    );
  }

  var triggers = ScriptApp.getProjectTriggers();
  triggers.forEach(function (trigger) {
    if (trigger.getHandlerFunction() === MONITOR_TRIGGER_FUNCTION) {
      ScriptApp.deleteTrigger(trigger);
    }
  });
  ScriptApp.newTrigger(MONITOR_TRIGGER_FUNCTION)
    .timeBased()
    .everyMinutes(1)
    .create();
}

function removePriceMonitor() {
  ScriptApp.getProjectTriggers().forEach(function (trigger) {
    if (trigger.getHandlerFunction() === MONITOR_TRIGGER_FUNCTION) {
      ScriptApp.deleteTrigger(trigger);
    }
  });
}

function monitorStockPrices() {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) {
    console.log("Previous price-monitor run is still active; skipping this run.");
    return;
  }

  try {
    var now = new Date();
    var localTime = Utilities.formatDate(now, MONITOR_TIME_ZONE, "HH:mm");
    var localDate = Utilities.formatDate(now, MONITOR_TIME_ZONE, "yyyyMMdd");
    var dayOfWeek = Number(Utilities.formatDate(now, MONITOR_TIME_ZONE, "u"));
    if (dayOfWeek > 5 || localTime < "09:00" || localTime > "13:30") {
      return;
    }
    if (getTaiwanMarketHolidays_().indexOf(localDate) !== -1) {
      console.log("Taiwan market is closed today; skipping price monitoring.");
      return;
    }

    var sheet = getSheet_();
    ensureHeaders_(sheet);
    var lastRow = sheet.getLastRow();
    if (lastRow < 2) {
      return;
    }

    var values = sheet.getRange(1, 1, lastRow, sheet.getLastColumn()).getValues();
    var headerIndexes = {};
    values[0].forEach(function (header, index) {
      headerIndexes[String(header).trim()] = index;
    });
    ["股號", "預計買股金額", "實際買股數量", "預計賣股金額"].forEach(function (header) {
      if (headerIndexes[header] === undefined) {
        throw new Error('工作表缺少必要欄位「' + header + '」。');
      }
    });

    var quoteCache = {};
    for (var rowIndex = 1; rowIndex < values.length; rowIndex++) {
      var row = values[rowIndex];
      var stockId = String(row[headerIndexes["股號"]] || "").trim().replace(/\.0$/, "");
      if (!stockId) {
        continue;
      }
      if (!/^\d{1,6}$/.test(stockId)) {
        throw new Error("無效的台股代號，第 " + (rowIndex + 1) + " 列：" + stockId);
      }
      if (!Object.prototype.hasOwnProperty.call(quoteCache, stockId)) {
        try {
          quoteCache[stockId] = getTaiwanStockPrice_(stockId, localDate);
        } catch (error) {
          console.error(
            "Failed to fetch quote for stock " + stockId + ": " + error.message
          );
          quoteCache[stockId] = null;
        }
      }

      var marketPrice = quoteCache[stockId];
      if (marketPrice === null) {
        console.log("No current-session quote for stock " + stockId + "; skipping alerts.");
        continue;
      }

      var stockName = headerIndexes["股名"] === undefined
        ? stockId
        : String(row[headerIndexes["股名"]] || stockId);
      var buyPrice = parseMonitorPrice_(row[headerIndexes["預計買股金額"]]);
      var actualBuyQuantity = parseMonitorPrice_(row[headerIndexes["實際買股數量"]]);
      var sellPrice = parseMonitorPrice_(row[headerIndexes["預計賣股金額"]]);
      var rowNumber = rowIndex + 1;
      var buyAlertKey = getMonitorAlertCountKey_(
        sheet, rowNumber, stockId, "buy", buyPrice
      );
      var sellAlertKey = getMonitorAlertCountKey_(
        sheet, rowNumber, stockId, "sell", sellPrice
      );
      var buyConditionMet = buyPrice > 0 && marketPrice <= buyPrice;
      var sellConditionMet = sellPrice > 0 && marketPrice >= sellPrice;

      if (actualBuyQuantity > 0) {
        PropertiesService.getScriptProperties().deleteProperty(buyAlertKey);
      } else if (buyConditionMet) {
        sendMonitorAlertUpToLimit_(
          buyAlertKey,
          "🟢 【買入警報】" + stockName + "(" + stockId + ")" +
          "\n當前股價: " + marketPrice +
          "\n已達到預計買入價: " + buyPrice
        );
      } else {
        PropertiesService.getScriptProperties().deleteProperty(buyAlertKey);
      }
      if (sellConditionMet) {
        sendMonitorAlertUpToLimit_(
          sellAlertKey,
          "🔴 【賣出警報】" + stockName + "(" + stockId + ")" +
          "\n當前股價: " + marketPrice +
          "\n已達到預計賣出價: " + sellPrice
        );
      } else {
        PropertiesService.getScriptProperties().deleteProperty(sellAlertKey);
      }
    }
  } finally {
    lock.releaseLock();
  }
}

function getMonitorAlertCountKey_(sheet, rowNumber, stockId, direction, targetPrice) {
  return "monitor_alert_count_" + [
    SpreadsheetApp.getActiveSpreadsheet().getId(),
    sheet.getSheetId(),
    rowNumber,
    stockId,
    direction,
    targetPrice
  ].join("_");
}

function sendMonitorAlertUpToLimit_(key, message) {
  var properties = PropertiesService.getScriptProperties();
  var count = Number(properties.getProperty(key) || 0);
  if (count >= MONITOR_MAX_ALERTS_PER_CONDITION) {
    return;
  }

  sendMonitorTelegram_(message);
  properties.setProperty(key, String(count + 1));
}

function getTaiwanMarketHolidays_() {
  var cache = CacheService.getScriptCache();
  var cachedHolidays = cache.get("twse_market_holidays");
  if (cachedHolidays) {
    return JSON.parse(cachedHolidays);
  }

  var response = UrlFetchApp.fetch(HOLIDAY_API_URL, { muteHttpExceptions: true });
  if (response.getResponseCode() !== 200) {
    throw new Error("讀取證交所休市日失敗，HTTP " + response.getResponseCode());
  }
  var entries = JSON.parse(response.getContentText());
  if (!Array.isArray(entries)) {
    throw new Error("證交所休市日 API 回傳格式錯誤。");
  }

  var currentYear = Number(Utilities.formatDate(new Date(), MONITOR_TIME_ZONE, "yyyy"));
  var foundCurrentYear = false;
  var holidays = [];
  entries.forEach(function (entry) {
    var match = String(entry.Date || "").match(/^(\d{3})(\d{2})(\d{2})$/);
    if (!match) {
      return;
    }
    var date = String(Number(match[1]) + 1911) + match[2] + match[3];
    if (Number(date.slice(0, 4)) === currentYear) {
      foundCurrentYear = true;
    }
    var description = String(entry.Description || "");
    var name = String(entry.Name || "");
    if (description.indexOf("放假") !== -1 || name.indexOf("市場無交易") !== -1) {
      holidays.push(date);
    }
  });
  if (!foundCurrentYear) {
    throw new Error("證交所休市日 API 未提供今年資料，為避免休市日誤報，已停止本次監控。");
  }

  cache.put("twse_market_holidays", JSON.stringify(holidays), 21600);
  return holidays;
}

function getTaiwanStockPrice_(stockId, localDate) {
  var exchangeCodes = ["tse_", "otc_"].map(function (exchange) {
    return exchange + stockId + ".tw";
  });
  var url = QUOTE_API_URL +
    "?ex_ch=" + encodeURIComponent(exchangeCodes.join("|")) +
    "&json=1&delay=0";
  var response = UrlFetchApp.fetch(url, {
    headers: {
      "Referer": "https://mis.twse.com.tw/stock/fibest.jsp?lang=zh_tw",
      "User-Agent": "Mozilla/5.0"
    },
    muteHttpExceptions: true
  });
  if (response.getResponseCode() !== 200) {
    throw new Error(
      "讀取台股行情失敗（" + stockId + "），HTTP " + response.getResponseCode()
    );
  }
  var payload = JSON.parse(response.getContentText());
  var quotes = payload.msgArray || [];
  for (var i = 0; i < quotes.length; i++) {
    if (quotes[i].d !== localDate) {
      continue;
    }
    var price = parseMonitorPrice_(quotes[i].z);
    if (price <= 0 && quotes[i].trade) {
      price = parseMonitorPrice_(quotes[i].trade.z);
    }
    if (price > 0) {
      return price;
    }
  }
  return null;
}

function parseMonitorPrice_(value) {
  if (value === null || value === undefined || String(value).trim() === "") {
    return 0;
  }
  var price = Number(String(value).replace(/,/g, "").trim());
  return isFinite(price) ? price : 0;
}

function sendMonitorTelegram_(message) {
  var properties = PropertiesService.getScriptProperties();
  var token = properties.getProperty("TELEGRAM_BOT_TOKEN");
  var chatId = properties.getProperty("TELEGRAM_CHAT_ID");
  if (!token || !chatId) {
    throw new Error(
      "請在 Apps Script 指令碼屬性設定 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID。"
    );
  }

  var response = UrlFetchApp.fetch(
    "https://api.telegram.org/bot" + token + "/sendMessage",
    {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify({ chat_id: chatId, text: message }),
      muteHttpExceptions: true
    }
  );
  var result = JSON.parse(response.getContentText());
  if (response.getResponseCode() < 200 || response.getResponseCode() >= 300 || !result.ok) {
    throw new Error("Telegram 通知發送失敗：" + (result.description || response.getResponseCode()));
  }
}
