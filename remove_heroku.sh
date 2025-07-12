#!/bin/sh
# Remove Heroku remote from local git config
heroku git:remote -a vq-everything-7122d08608a7 --remove || true
# Destroy the Heroku app (irreversible!)
heroku apps:destroy vq-everything-7122d08608a7 --confirm vq-everything-7122d08608a7
