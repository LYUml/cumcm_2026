import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = "/Users/lml/Desktop/cumcm_2026";
const templatePath = `${root}/00_problem/appendix/附件5/result4-2.xlsx`;
const outputPath = `${root}/04_q4/outputs/final/result4-2.xlsx`;
const previewDir = `${root}/04_q4/outputs/final/previews`;
const mode = process.argv[2] ?? "build";

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(templatePath));

if (mode === "inspect") {
  const overview = await workbook.inspect({
    kind: "workbook,sheet,table", maxChars: 10000,
    tableMaxRows: 8, tableMaxCols: 10, tableMaxCellChars: 100,
  });
  process.stdout.write(overview.ndjson + "\n");
  await fs.mkdir(previewDir, { recursive: true });
  for (const name of ["计划购电量", "充放电量", "紧急购电量"]) {
    const preview = await workbook.render({ sheetName: name, autoCrop: "all", scale: 1.2, format: "png" });
    await fs.writeFile(`${previewDir}/template_${name}.png`, new Uint8Array(await preview.arrayBuffer()));
  }
  process.exit(0);
}

const payload = JSON.parse(await fs.readFile(`${root}/04_q4/outputs/final/result4_2_payload.json`, "utf8"));
const plan = workbook.worksheets.getItem("计划购电量");
const battery = workbook.worksheets.getItem("充放电量");
const emergency = workbook.worksheets.getItem("紧急购电量");
const toDate = value => value ? new Date(value) : null;

const planRows = payload.plan.map(row => [toDate(row[0]), ...row.slice(1)]);
plan.getRange("A2").write(planRows);

const batteryRows = payload.battery.map(row => [toDate(row[0]), ...row.slice(1)]);
battery.getRange(`A2:F${batteryRows.length + 1}`).copyFrom(battery.getRange("A2:F2"), "all");
battery.getRange("A2").write(batteryRows);
battery.getRange(`A2:A${batteryRows.length + 1}`).setNumberFormat("m/d/yy");

const oldEmergency = emergency.getUsedRange();
if (oldEmergency) emergency.getRange("A2:C10000").clear({ applyTo: "contents" });
const emergencyRows = payload.emergency.map(row => [toDate(row[0]), row[1], row[2]]);
emergency.getRange(`A2:C${emergencyRows.length + 1}`).copyFrom(emergency.getRange("A2:C2"), "all");
emergency.getRange("A2").write(emergencyRows);
emergency.getRange(`A2:A${emergencyRows.length + 1}`).setNumberFormat("m/d/yy");

await workbook.recalculate();
await fs.mkdir(previewDir, { recursive: true });
const checks = [];
for (const [name, range] of [
  ["计划购电量", "A1:J6"],
  ["计划购电量", "EN1:EQ6"],
  ["充放电量", "A1:F14"],
  ["紧急购电量", "A1:C20"],
]) {
  const result = await workbook.inspect({
    kind: "table", range: `${name}!${range}`,
    include: "values,formulas", tableMaxRows: 20, tableMaxCols: 150,
    maxChars: 20000,
  });
  checks.push(result.ndjson);
  const preview = await workbook.render({ sheetName: name, range, scale: 1.5, format: "png" });
  await fs.writeFile(`${previewDir}/final_${name}.png`, new Uint8Array(await preview.arrayBuffer()));
}
const errors = await workbook.inspect({
  kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 }, summary: "final formula error scan",
});
checks.push(errors.ndjson);
await fs.writeFile(`${root}/04_q4/outputs/final/result4_2_workbook_inspection.ndjson`, checks.join("\n"));
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
process.stdout.write(JSON.stringify({ outputPath, planRows: planRows.length,
  batteryRows: batteryRows.length, emergencyRows: emergencyRows.length }) + "\n");
