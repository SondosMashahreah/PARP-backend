// Run from backend: node scripts/sync_assistant_knowledge.mjs ../frontend
import { resolve, dirname } from 'node:path'
import { pathToFileURL, fileURLToPath } from 'node:url'
import { writeFile } from 'node:fs/promises'
const frontend=resolve(process.argv[2] || '../frontend')
const load=async path=>import(pathToFileURL(resolve(frontend,path)).href)
const ar=await load('src/features/platform/data/platformContent.js')
const en=await load('src/features/platform/data/platformContent.en.js')
const docs=[]
for(const page of ['Guide','Template','About','Training','Library','Support']) {
  const {content}=await load(`src/pages/${page}/${page}Page.content.js`)
  docs.push({id:page.toLowerCase(),path:`/${page.toLowerCase()}`,guidance:['Guide','Template'].includes(page),
    source:`src/pages/${page}/${page}Page.content.js`,content_type:'Informational page copy, not evidence that every advertised feature or example record exists.',content})
}
docs.push({id:'actual-guide-and-template',path:'/guide',guidance:true,source:'src/features/platform/data/platformContent.js + platformContent.en.js',
  guide_ar:ar.GUIDE_CHAPTERS,guide_en:en.GUIDE_CHAPTERS,template_ar:ar.TEMPLATE_STEPS,template_en:en.TEMPLATE_STEPS,
  official_numeric_rubric:false,
  evaluation_method:'Advisory only: for each template element, cite evidence from the available text, identify missing evidence and suggest an actionable revision. Do not invent numeric scores, official weights or acceptance thresholds. Do not mistake completeness for scientific quality.'})
docs.push({id:'current-workflows',path:'/assistant',guidance:true,content:{
  research:'Draft -> submit with file -> committee review -> revisions or acceptance -> offline payment request -> admin confirms payment even if zero -> researcher publishes. Electronic payment is disabled.',
  practice:'Draft -> review -> acceptance -> researcher publishes free; public reading is free.',
  schools:'Registration means a distinct school with an active teacher/researcher or school manager and approved affiliation. Map catalog entries are not registrations.',
  excellence:'Admin creates card, selects published research and conference, uploads portrait and enables visibility. Card opens public researcher profile. Hidden cards and unpublished research are not public.',
  conference:'Scientific committee creates conferences, reviews participations and sends internal notices. Organizing committee is limited to its assigned conference.',
  writing:'Submission requires title, research field, problem, abstract (each at least two characters) and PDF/Word file up to 25MB. Draft saves preserve text only. Supervisor role has been removed.',
  news:'News is live in /api/news. Guests and all roles can read published news and full details at /news?article=ID. Use read_platform dataset news for current records and totals. Only system_admin can create, upload an image, publish, edit, unpublish or delete news through Dashboard > News. Drafts are private. An image, title and body are required to publish.',
  limitations:'No official numeric review rubric is configured. Public repository shows research abstracts; full research files are not free by default. The assistant cannot read uploaded document bytes, execute platform mutations, or treat illustrative frontend statistics as live records.'}})
const output=resolve(dirname(fileURLToPath(import.meta.url)),'../app/data/assistant_knowledge.json')
await writeFile(output,JSON.stringify(docs,null,2)+'\n')
console.log(`Synced ${docs.length} knowledge records from ${frontend}`)
