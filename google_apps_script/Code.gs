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
  "英文股名"
];

function getSheet_() {
  return SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
}

function ensureHeaders_(sheet) {
  if (sheet.getLastRow() === 0) {
    sheet.getRange(1, 1, 1, SHEET_HEADERS.length).setValues([SHEET_HEADERS]);
    sheet.setFrozenRows(1);
    return;
  }

  var firstRow = sheet
    .getRange(1, 1, 1, Math.max(sheet.getLastColumn(), 1))
    .getDisplayValues()[0]
    .map(function (value) {
      return String(value).trim();
    });
  var hasHeaders = firstRow[0] === "股號" && firstRow[1] === "股名";

  if (!hasHeaders) {
    sheet.insertRowBefore(1);
  }

  sheet.getRange(1, 1, 1, SHEET_HEADERS.length).setValues([SHEET_HEADERS]);
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
    result.push(record);
  }

  return jsonOutput_(result);
}

function doPost(e) {
  try {
    var sheet = getSheet_();
    ensureHeaders_(sheet);

    var contents = JSON.parse(e.postData.contents);
    if (!contents || !Array.isArray(contents.row)) {
      throw new Error("Request body must contain a row array.");
    }

    var rowData = contents.row.slice(0, SHEET_HEADERS.length);
    while (rowData.length < SHEET_HEADERS.length) {
      rowData.push("");
    }
    sheet.appendRow(rowData);

    return jsonOutput_({ result: "success" });
  } catch (error) {
    return jsonOutput_({ result: "error", message: error.toString() });
  }
}
