#!/usr/bin/env node
import { runPluginCli } from '@img2threejs/img2/plugin-cli'

process.exitCode = await runPluginCli({ packageUrl: new URL('../package.json', import.meta.url) })