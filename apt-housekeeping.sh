#!/usr/bin/env bash

aptitude search ?obsolete
aptitude search ?config-files
cruft
cruft-ng
aptitude search '~S ~i !~ODebian !~o'
