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
    'Full Xcode is required for the macOS Secure Enclave gate. Install/open Xcode once, sign in under Xcode > Settings > Apple Accounts, select a Team for the HAAApprover target, then rerun. Command Line Tools alone cannot create the provisioning profile required by the Data Protection Keychain.',
  );
}

export function buildProvisionedMacApprover({ repoRoot, buildRoot }) {
  const developerDir = resolveDeveloperDir();
  const env = { ...process.env, DEVELOPER_DIR: developerDir };
  const explicitTeamId = process.env.HAA_APPLE_TEAM_ID?.trim() || null;
  const bundleId = process.env.HAA_APPLE_BUNDLE_ID ?? 'com.krukmat.haa.approver';
  const project = join(repoRoot, 'macos', 'haa-approver-app', 'HAAApprover.xcodeproj');
  const outputDir = join(buildRoot, 'haa-approver-app');

  const nodeMajor = Number(process.versions.node.split('.')[0]);
  if (nodeMajor < 24) {
    console.warn(`⚠ HAA declares Node >=24; current validation runtime is Node ${process.versions.node}. Use Node 24 for CI parity.`);
  }

  if (explicitTeamId) {
    console.log(`✓ macOS signing team override: ${explicitTeamId}`);
  } else {
    console.log('✓ macOS signing team: using the Team selected in Xcode Signing & Capabilities');
  }
  console.log(`✓ macOS approver bundle id: ${bundleId}`);

  const buildArguments = [
    '-project', project,
    '-target', 'HAAApprover',
    '-configuration', 'Release',
    '-allowProvisioningUpdates',
    'CODE_SIGN_STYLE=Automatic',
    `PRODUCT_BUNDLE_IDENTIFIER=${bundleId}`,
    `CONFIGURATION_BUILD_DIR=${outputDir}`,
  ];
  if (explicitTeamId) buildArguments.push(`DEVELOPMENT_TEAM=${explicitTeamId}`);
  buildArguments.push('build');

  try {
    execFileSync('/usr/bin/xcodebuild', buildArguments, { cwd: repoRoot, env, stdio: 'inherit' });
  } catch (error) {
    throw new Error(
      'Xcode automatic signing failed. Open macos/haa-approver-app/HAAApprover.xcodeproj, select target HAAApprover > Signing & Capabilities, enable Automatically manage signing and select your Personal Team. Resolve any red signing error in Xcode, then rerun npm run validate:agent-macos. HAA_APPLE_TEAM_ID is optional and should only be used when you intentionally want to override the Xcode-selected team.',
      { cause: error },
    );
  }

  const appPath = join(outputDir, 'HAAApprover.app');
  const executablePath = join(appPath, 'Contents', 'MacOS', 'HAAApprover');
  const profilePath = join(appPath, 'Contents', 'embedded.provisionprofile');
  if (!existsSync(executablePath)) throw new Error(`Provisioned approver executable was not produced at ${executablePath}`);
  if (!existsSync(profilePath)) {
    throw new Error('Xcode built the app without an embedded provisioning profile. Open the project in Xcode and confirm that the HAAApprover target shows your Personal Team with Automatically manage signing enabled and no signing errors.');
  }

  execFileSync('/usr/bin/codesign', ['--verify', '--strict', appPath], { env, stdio: 'inherit' });
  const entitlements = commandOutput('/usr/bin/codesign', ['-d', '--entitlements', ':-', appPath], { env }) ?? '';
  if (!entitlements.includes('keychain-access-groups') || !entitlements.includes('application-identifier')) {
    throw new Error(`Provisioned approver is missing required keychain/application identity entitlements. codesign output:\n${entitlements}`);
  }

  console.log('✓ Provisioned macOS approver built and code signature verified');
  return { appPath, executablePath, teamId: explicitTeamId, bundleId };
}
