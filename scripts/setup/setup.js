const fs = require('fs');
const path = require('path');

const baseDir = r'c:\Users\kenyb\Desktop\GEMINI\Trading-qlearning\Trading-qlearning';
process.chdir(baseDir);

const dirs = [
    "core", "manager", "strategies/pinescript", "data/qlearning",
    "data/trades/archive", "data/reports", "dashboard/output", "dashboard/history",
    "utils", "scripts", "docs", "tests/fixtures", "logs/dry_run", "signals"
];

console.log("Creating directories...");
for (const d of dirs) {
    try {
        fs.mkdirSync(d, { recursive: true });
        console.log(`  created: ${d}`);
    } catch (e) {
        console.log(`  error: ${d} - ${e.message}`);
    }
}

console.log("\nCreating __init__.py files...");
for (const pkg of ["core", "manager", "strategies", "utils", "tests"]) {
    const p = path.join(pkg, "__init__.py");
    try {
        if (!fs.existsSync(p)) {
            fs.writeFileSync(p, "");
            console.log(`  created: ${pkg}/__init__.py`);
        }
    } catch (e) {
        console.log(`  error: ${p} - ${e.message}`);
    }
}

console.log("\nCreating .gitkeep files...");
for (const d of ["data/qlearning", "data/trades", "data/reports",
                   "dashboard/output", "dashboard/history", "logs/dry_run", "signals"]) {
    const p = path.join(d, ".gitkeep");
    try {
        if (!fs.existsSync(p)) {
            fs.writeFileSync(p, "");
            console.log(`  created: ${d}/.gitkeep`);
        }
    } catch (e) {
        console.log(`  error: ${p} - ${e.message}`);
    }
}

console.log("\nSetup complete!");
