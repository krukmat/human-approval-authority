import { execFileSync, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

function commandOutput(command, args, options = {}) {
  const result = spawnSync(command, args, { encoding: 'utf8', ...options });
  if (result.status !== 0) return null;
  return `${result.stdout ?? ''}${result.stderr ?? ''}`;
}

function resolveDeveloperDir() {
  if (process.env.DEVELOPER_DIR) return process.env.DEVELOPER_DIR;

  const selected = commandOutput('/usr/bin/xcode-select', ['-p'])?.trim();
  if (selected && !selected.endsWith('/CommandLineTools')) return selected;

  const standardXcode = '/Applications/Xcode.app/Contents/Developer';
  if (existsSync(join(standardXcode, 'usr/bin/xcodebuild'))) return standardXcode;

  throw new Error(
    'Full Xcode is required for the macOS Secure Enclave gate. Install/open Xcode once, sign in under Xcode > Settings > Accounts, then rerun. Command Line Tools alone cannot create the provisioning profile required by the Data Protection Keychain.',
  );
}

function resolveTeamId(env) {
  if (process.env.HAA_APPLE_TEAM_ID) return process.env.HAA_APPLE_TEAM_ID;

  const identities = commandOutput('/usr/bin/security', ['find-identity', '-v', '-p', 'codesigning'], { env }) ?? '';
  const developmentTeams = [...identities.matchAll(/Apple Development:[^\n]*\(([A-Z0-9]{10})\)/g)].map((match) => match[1]);
  const unique = [...new Set(developmentTeams)];
  if (unique.length === 1) return unique[0];
  if (unique.length > 1) {
    throw new Error(`Multiple Apple Development teams detected (${unique.join(', ')}). Set HAA_APPLE_TEAM_ID to the team to use.`);
  }

  throw new Error(
    'No Apple Development signing identity was detected. Open Xcode > Settings > Accounts, sign in, create an Apple Development certificate for your team, then rerun. You can also set HAA_APPLE_TEAM_ID explicitly once the identity exists.',
  );
}

export function buildProvisionedMacApprover({ repoRoot, buildRoot }) {
  const developerDir = resolveDeveloperDir();
  const env = { ...process.env, DEVELOPER_DIR: developerDir };
  const teamId = resolveTeamId(env);
  const bundleId = process.env.HAA_APPLE_BUNDLE_ID ?? 'com.krukmat.haa.approver';
  const project = join(repoRoot, 'macos', 'haa-approver-app', 'HAAApprover.xcodeproj');
  const outputDir = join(buildRoot, 'haa-approver-app');

  const nodeMajor = Number(process.versions.node.split('.')[0]);
  if (nodeMajor < 24) {
    console.warn(`⚠ HAA declares Node >=24; current validation runtime is Node ${process.versions.node}. The macOS signing fix is independent, but use Node 24 for CI parity.`);
  }

  console.log(`✓ macOS signing team: ${teamId}`);
  console.log(`✓ macOS approver bundle id: ${bundleId}`);

  execFileSync(
    '/usr/bin/xcodebuild',
    [
      '-project', project,
      '-target', 'HAAApprover',
      '-configuration', 'Release',
      '-allowProvisioningUpdates',
      `DEVELOPMENT_TEAM=${teamId}`,
      'CODE_SIGN_STYLE=Automatic',
      `PRODUCT_BUNDLE_IDENTIFIER=${bundleId}`,
      `CONFIGURATION_BUILD_DIR=${outputDir}`,
      'build',
    ],
    { cwd: repoRoot, env, stdio: 'inherit' },
  );

  const appPath = join(outputDir, 'HAAApprover.app');
  const executablePath = join(appPath, 'Contents', 'MacOS', 'HAAApprover');
  const profilePath = join(appPath, 'Contents', 'embedded.provisionprofile');
  if (!existsSync(executablePath)) throw new Error(`Provisioned approver executable was not produced at ${executablePath}`);
  if (!existsSync(profilePath)) {
    throw new Error('Xcode built the app without an embedded provisioning profile. The Secure Enclave path requires a provisioned app identity; verify the selected Apple Development team and automatic signing configuration.');
  }

  execFileSync('/usr/bin/codesign', ['--verify', '--strict', appPath], { env, stdio: 'inherit' });
  const entitlements = commandOutput('/usr/bin/codesign', ['-d', '--entitlements', ':-', appPath], { env }) ?? '';
  if (!entitlements.includes('keychain-access-groups') || !entitlements.includes('application-identifier')) {
    throw new Error(`Provisioned approver is missing required keychain/application identity entitlements. codesign output:\n${entitlements}`);
  }

  console.log('✓ Provisioned macOS approver built and code signature verified');
  return { appPath, executablePath, teamId, bundleId };
}
