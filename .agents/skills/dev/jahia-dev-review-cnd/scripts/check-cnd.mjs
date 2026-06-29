#!/usr/bin/env node
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

function findCndFiles(dir) {
  const results = [];
  function walk(current) {
    try {
      const stat = statSync(current);
      if (stat.isFile()) {
        if (current.endsWith(".cnd")) results.push(current);
        return;
      }
      for (const entry of readdirSync(current, { withFileTypes: true })) {
        if (entry.isDirectory() && entry.name !== "node_modules" && entry.name !== ".git") {
          walk(join(current, entry.name));
        } else if (entry.isFile() && entry.name.endsWith(".cnd")) {
          results.push(join(current, entry.name));
        }
      }
    } catch {
      // skip unreadable paths
    }
  }
  walk(dir);
  return results;
}

function checkFile(filePath, content) {
  const issues = [];
  const lines = content.split("\n");

  lines.forEach((line, i) => {
    const lineNum = i + 1;
    const trimmed = line.trim();
    if (trimmed.startsWith("//") || trimmed.startsWith("<")) return;

    // rawStringLink
    if (
      /^-\s+\w*(Url|Href|Link)\s+\(string[,)]/i.test(trimmed) &&
      !/choicelist\[linkTypeInitializer\]/.test(trimmed)
    ) {
      const propName = trimmed.match(/^-\s+(\w+)/)?.[1] ?? "unknown";
      issues.push({
        file: filePath, line: lineNum,
        pattern: "rawStringLink",
        message: `"${propName}" uses (string) for a link/url — use choicelist[linkTypeInitializer]`,
        fix: "Replace with: - j:linkType (string, choicelist[linkTypeInitializer]) mandatory",
      });
    }

    // rawTitleProp
    if (/^-\s+(title|heroTitle|pageTitle|sectionTitle)\s+\(string[,)]/i.test(trimmed)) {
      const propName = trimmed.match(/^-\s+(\w+)/)?.[1] ?? "unknown";
      issues.push({
        file: filePath, line: lineNum,
        pattern: "rawTitleProp",
        message: `"${propName}" is a plain string — extend mix:title instead`,
        fix: "Add mix:title to the type declaration and remove this property",
      });
    }

    // weakrefNoConstraint: (weakreference) with no < constraint on same line.
    // LOCAL ADAPTATION (jahiaMigration): exempt query-root reference fields —
    // startNode/excludeNodes legitimately point to arbitrary containers (the
    // documented "full node browser" convention), so a single type constraint
    // would be wrong. See .agents/AGENTIC-SYNC.md.
    const __wname = (trimmed.match(/^-\s*([A-Za-z0-9_:]+)\s*\(weakreference/) || [])[1];
    const __EXEMPT_WEAKREF = new Set(["startNode", "excludeNodes"]);
    // A category[...] selector (taxonomy) or a non-image file picker constrains the
    // weakref by selector — a `< type` constraint is not the right tool there.
    const __selectorConstrained =
      /category\[/.test(trimmed) || /picker\[type=['"]file['"]\]/.test(trimmed);
    if (
      /\(weakreference[,)]/.test(trimmed) &&
      !/<\s*\S/.test(trimmed) &&
      !__EXEMPT_WEAKREF.has(__wname) &&
      !__selectorConstrained
    ) {
      issues.push({
        file: filePath, line: lineNum,
        pattern: "weakrefNoConstraint",
        message: "Unconstrained weakreference — add a type constraint",
        fix: "Add e.g. (weakreference, picker[type='image']) < jmix:image",
      });
    }

    // weakrefWrongConstraint
    if (/< ['"]jnt:file['"]/.test(trimmed)) {
      issues.push({
        file: filePath, line: lineNum,
        pattern: "weakrefWrongConstraint",
        message: "< 'jnt:file' (quoted) does not enforce image type",
        fix: "Replace with < jmix:image for images",
      });
    }

    // missingI18n: user-visible string without i18n
    if (
      /^-\s+\w+\s+\(string(,\s*(textarea|richtext))?[,)]/.test(trimmed) &&
      !/ i18n/.test(trimmed) &&
      !/^-\s+j:/.test(trimmed) &&
      /(title|text|label|description|subtitle|caption|alt|heading|summary|excerpt|body)/i.test(trimmed) &&
      // config values are not translatable content (theme tokens: colors, font names)
      !/^-\s+\w*(color|font|theme)/i.test(trimmed)
    ) {
      issues.push({
        file: filePath, line: lineNum,
        pattern: "missingI18n",
        message: "User-visible string property missing i18n",
        fix: "Add i18n keyword after the type declaration",
      });
    }

    // directDroppable: concrete type (not mixin) extending jmix:droppableContent
    if (trimmed.startsWith("[") && /jmix:droppableContent/.test(trimmed) && !/\bmixin\b/.test(trimmed)) {
      issues.push({
        file: filePath, line: lineNum,
        pattern: "directDroppable",
        message: "Extends jmix:droppableContent directly — always extend the module component mixin",
        fix: "Replace jmix:droppableContent with nsmix:component (or your module's equivalent)",
      });
    }

    // studioOnly
    if (/jmix:studioOnly/.test(trimmed)) {
      issues.push({
        file: filePath, line: lineNum,
        pattern: "studioOnly",
        message: "jmix:studioOnly causes silent rendering issues",
        fix: "Replace with jmix:hiddenType",
      });
    }

    // redundantImageAlt: imageAlt as plain string — image node already has jcr:title
    if (/^-\s+imageAlt\s+\(string[,)]/i.test(trimmed)) {
      issues.push({
        file: filePath, line: lineNum,
        pattern: "redundantImageAlt",
        message: '"imageAlt" is redundant — the image node\'s jcr:title (mix:title) serves as alt text',
        fix: 'Remove imageAlt. In the view, use image.getPropertyAsString("jcr:title") for alt text',
      });
    }

    // missingRatingConstraint: rating (long) without a range constraint
    if (/^-\s+rating\s+\(long[,)]/i.test(trimmed) && !/<\s*"?\[/.test(trimmed)) {
      issues.push({
        file: filePath, line: lineNum,
        pattern: "missingRatingConstraint",
        message: '"rating" (long) has no range constraint — unconstrained ratings cause data integrity issues',
        fix: 'Add: < "[1,5]"',
      });
    }

    // choicelistOrder: value constraints (< 'a','b') placed BEFORE the default (= 'x').
    // Jahia's CND reader wants: = 'default' <keywords> < 'constraints'. Reversed order
    // throws at install (a generic IOException). `<\s*'` matches only VALUE constraints,
    // not type constraints like `< jmix:image` (no quote).
    if (trimmed.startsWith("-")) {
      const ltIdx = trimmed.search(/<\s*'/);
      const eqIdx = trimmed.search(/=\s*'/);
      if (ltIdx !== -1 && eqIdx !== -1 && ltIdx < eqIdx) {
        const propName = trimmed.match(/^-\s+([\w:]+)/)?.[1] ?? "unknown";
        issues.push({
          file: filePath, line: lineNum,
          pattern: "choicelistOrder",
          message: `"${propName}": value constraints (< '...') appear BEFORE the default (= '...') — Jahia rejects this order at install`,
          fix: "Reorder to: = 'default' autocreated < 'a', 'b'",
        });
      }
    }

    // subnodetypesWhitespace: a node-type CSV in an initializer with a space after a
    // comma → the engine generates a Require-Capability for a node type with a leading
    // space (nodetypes= jmix:mainResource) that never resolves → OSGi BundleException.
    if (/(subnodetypes|nodetypes)\s*=\s*'[^']*,\s/.test(trimmed)) {
      issues.push({
        file: filePath, line: lineNum,
        pattern: "subnodetypesWhitespace",
        message: "node-type CSV has a space after a comma — generates an unresolvable nodetypes capability",
        fix: "Remove spaces inside the CSV: 'jnt:page,jmix:mainResource' (no space after the comma)",
      });
    }
  });

  // singleHardcodedCta: check whole-file type blocks
  const typeBlocks = content.split(/(?=^\[)/m);
  for (const block of typeBlocks) {
    if (!block.trim().startsWith("[")) continue;
    const hasCtaLabel = /^\s*-\s+cta(Text|Label|ButtonText|ButtonLabel)\s+\(/im.test(block);
    const hasCtaLink = /^\s*-\s+cta(Link|Url|Href|ButtonLink|ButtonUrl)\s+\(/im.test(block);
    const hasChildNodes = /^\s*\+\s+/.test(block);
    if (hasCtaLabel && hasCtaLink && !hasChildNodes) {
      const typeName = block.match(/^\[(\S+)\]/m)?.[1] ?? "unknown";
      const typeLineIdx = lines.findIndex((l) => l.includes(`[${typeName}]`));
      issues.push({
        file: filePath,
        ...(typeLineIdx >= 0 ? { line: typeLineIdx + 1 } : {}),
        pattern: "singleHardcodedCta",
        message: `${typeName}: flat ctaText+ctaLink forces a single CTA — model as child nodes`,
        fix: "Remove ctaText and ctaLink. Add: + * (ns:cta). Create a [ns:cta] type with label + j:linkType",
      });
    }
  }

  return issues;
}

// Cross-file checks: a duplicate type definition, or a MODULE-defined type used in a
// subnodetypes initializer (the self-referencing Require-Capability trap). Both make the
// bundle fail to install/resolve — invisible to per-line linting.
function checkAcrossFiles(fileContents) {
  const issues = [];
  const definedAt = new Map(); // typeName -> [{file,line}]
  const subnodeRefs = [];      // {file, line, refs:[typeName]}

  for (const { file, content } of fileContents) {
    content.split("\n").forEach((line, i) => {
      const t = line.trim();
      const def = t.match(/^\[([\w]+:[\w]+)\]/);
      if (def) {
        if (!definedAt.has(def[1])) definedAt.set(def[1], []);
        definedAt.get(def[1]).push({ file, line: i + 1 });
      }
      const sub = t.match(/subnodetypes\s*=\s*'([^']*)'/);
      if (sub) {
        const refs = sub[1].split(",").map((s) => s.trim()).filter(Boolean);
        subnodeRefs.push({ file, line: i + 1, refs });
      }
    });
  }

  // duplicateType — same [ns:type] declared in 2+ places
  for (const [type, locs] of definedAt) {
    if (locs.length > 1) {
      issues.push({
        file: locs[0].file, line: locs[0].line,
        pattern: "duplicateType",
        message: `${type} is defined ${locs.length}× (${locs.map((l) => `${l.file}:${l.line}`).join(", ")}) — a duplicate type makes Jahia's CND reader throw at install`,
        fix: "Keep ONE definition (in the component's own dir if it has a view); remove the others",
      });
    }
  }

  // selfRefSubnodetype — a MODULE-defined type/mixin referenced in subnodetypes generates
  // a Require-Capability for a type the bundle provides → unresolvable self-reference.
  for (const ref of subnodeRefs) {
    for (const r of ref.refs) {
      if (definedAt.has(r)) {
        issues.push({
          file: ref.file, line: ref.line,
          pattern: "selfRefSubnodetype",
          message: `subnodetypes references "${r}", which this module DEFINES — a self-referencing nodetypes capability the bundle can't resolve`,
          fix: "Target a built-in marker instead (e.g. jmix:mainResource); have listable types extend it rather than a module mixin",
        });
      }
    }
  }

  return issues;
}

export function checkCndFiles(projectDir) {
  const files = findCndFiles(projectDir);
  const allIssues = [];
  const fileContents = [];

  for (const file of files) {
    try {
      const content = readFileSync(file, "utf-8");
      fileContents.push({ file, content });
      allIssues.push(...checkFile(file, content));
    } catch {
      // skip unreadable files
    }
  }
  allIssues.push(...checkAcrossFiles(fileContents));

  return { score: Math.exp(-allIssues.length * 0.5), issues: allIssues, filesChecked: files.length };
}

if (import.meta.main) {
  const targetPath = resolve(process.argv[2] ?? ".");
  const { score, issues, filesChecked } = checkCndFiles(targetPath);

  console.log(`\nCND Review: ${filesChecked} file${filesChecked !== 1 ? "s" : ""} checked\n`);

  if (issues.length > 0) {
    console.log(`ISSUES (${issues.length}):`);
    for (const issue of issues) {
      const loc = issue.line ? `${issue.file}:${issue.line}` : issue.file;
      console.log(`  [${issue.pattern}] ${loc}`);
      console.log(`    ${issue.message}`);
      console.log(`    Fix: ${issue.fix}`);
    }
    console.log();
  }

  const verdict = issues.length > 0 ? "FAIL" : "PASS";
  console.log(`Result: ${verdict} (score=${score.toFixed(2)})`);
  process.exit(issues.length > 0 ? 1 : 0);
}
