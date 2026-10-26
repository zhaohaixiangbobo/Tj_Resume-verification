/**
 * 将已核实的院校字典勘误写入修订版工作簿。
 * 仅修改指定名称所在行，保留原有工作表、格式、筛选和冻结窗格。
 */
import fs from 'node:fs/promises';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const inputPath = 'D:/8-烟草/2025开发工作/2027年度资格审查/qualification_review/outputs/20261026_完成版/院校层次与QS2027前200中英文.xlsx';
const outputPath = 'D:/8-烟草/2025开发工作/2027年度资格审查/qualification_review/outputs/20261026_完成版/院校层次与QS2027前200中英文_修订.xlsx';
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));

function rows(sheet, range) {
  return sheet.getRange(range).values;
}
function findRow(values, name, colIndex) {
  const index = values.findIndex((row, i) => i > 0 && row[colIndex] === name);
  if (index < 0) throw new Error(`未找到：${name}`);
  return index + 1;
}

const qs = wb.worksheets.getItem('QS2027前200中英文');
const qsValues = rows(qs, 'A1:K201');
const fixes = [
  ['City University of Hong Kong (CityUHK)', 'Kowloon, Hong Kong SAR China', null],
  ['The University of Sheffield', 'Sheffield, United Kingdom', null],
  ['Universität Heidelberg', 'Heidelberg, Germany', null],
  ['Farabi University (former Al - Farabi Kazakh National University)', 'Almaty, Kazakhstan', 'Al-Farabi Kazakh National University'],
  ['Politecnico di Milano', 'Milan, Italy', null],
  ['University of Alberta', 'Edmonton, Canada', null],
  ['Queen Mary University of London', 'London, United Kingdom', null],
  ['Lancaster University', 'Lancaster, United Kingdom', null],
];
for (const [oldName, location, newName] of fixes) {
  const row = findRow(qsValues, oldName, 4);
  if (newName) {
    qs.getRange(`D${row}`).values = [['阿里-法拉比哈萨克国立大学']];
    qs.getRange(`E${row}`).values = [[newName]];
  }
  qs.getRange(`F${row}`).values = [[location]];
}

const domestic = wb.worksheets.getItem('国内本科及以上');
const domesticValues = rows(domestic, 'A1:O1416');
const bnuRow = findRow(domesticValues, '北京师范大学珠海分校', 0);
domestic.getRange(`K${bnuRow}`).values = [['民办；2021年停止招生、2024年终止办学，历史名录保留']];
const nudtRow = findRow(domesticValues, '国防科技大学', 0);
domestic.getRange(`E${nudtRow}`).values = [['本科']];

const notes = wb.worksheets.getItem('使用说明');
notes.getRange('A16:B17').values = [
  ['北京师范大学珠海分校', '2021年停止招生、2024年终止办学；为识别历史学历名称而保留为民办独立学院，不按北京师范大学本部层次计分。来源：https://news.bnu.edu.cn/zx/zhxw/109390.htm'],
  ['本次修订', '清理QS城市国家地区格式；法拉比大学统一为 Al-Farabi Kazakh National University／阿里-法拉比哈萨克国立大学；国防科技大学办学层次统一为“本科”。'],
];

wb.recalculate();
const check = await wb.inspect({kind:'table', range:'QS2027前200中英文!A50:K55', include:'values,formulas', tableMaxRows:6, tableMaxCols:11});
const errorScan = await wb.inspect({kind:'match', searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options:{useRegex:true,maxResults:30}, summary:'修订后公式错误检查'});
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(outputPath);
const preview = await wb.render({sheetName:'QS2027前200中英文', range:'A50:K55', scale:1, format:'png'});
await fs.writeFile('D:/8-烟草/2025开发工作/2027年度资格审查/qualification_review/outputs/20261026_完成版/院校字典修订预览.png', new Uint8Array(await preview.arrayBuffer()));
console.log(JSON.stringify({check:check.ndjson, errors:errorScan.ndjson, outputPath}));
