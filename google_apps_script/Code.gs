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
    sheet.appendRow(rowData);

    return jsonOutput_({ result: "success" });
  } catch (error) {
    return jsonOutput_({ result: "error", message: error.toString() });
  }
}
