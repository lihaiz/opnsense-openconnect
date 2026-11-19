<?php

/*
 * Copyright (C) 2018 Michael Muenz <m.muenz@gmail.com>
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimer.
 *
 * 2. Redistributions of source code must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES
 * ARE DISCLAIMED. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT,
 * INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES.
 */

/**
 * Return the list of configured instances (associative arrays).
 */
function openconnect_instances()
{
    $result = array();
    $configObj = \OPNsense\Core\Config::getInstance()->object();
    $instances = $configObj->OPNsense->openconnect->instances;
    if ($instances === null) {
        return $result;
    }
    $idx = 0;
    foreach ($instances->children() as $instance) {
        $enabled = ((string)$instance->enabled == '1');
        $iface = trim((string)$instance->interface);
        if ($iface == '') {
            $iface = 'ocvpn' . ($idx + 1);
        }
        $result[] = array(
            'enabled' => $enabled,
            'iface' => $iface,
            'name' => trim((string)$instance->name) ?: $iface,
        );
        $idx++;
    }
    return $result;
}

function openconnect_enabled()
{
    foreach (openconnect_instances() as $inst) {
        if ($inst['enabled']) {
            return true;
        }
    }
    return false;
}

function openconnect_services()
{
    $services = array();

    if (openconnect_enabled()) {
        $services[] = array(
            'description' => gettext('OpenConnect'),
            'configd' => array(
                'restart' => array('openconnect restart'),
                'start' => array('openconnect start'),
                'stop' => array('openconnect stop'),
            ),
            'name' => 'openconnect',
            'pidfile' => '/var/run/openconnect.pid'
        );
    }

    return $services;
}

function openconnect_interfaces()
{
    $interfaces = array();

    foreach (openconnect_instances() as $inst) {
        if (!$inst['enabled']) {
            continue;
        }
        $if = $inst['iface'];
        $oic = array('enable' => true);
        $oic['if'] = $if;
        $oic['descr'] = 'OpenConnect ' . $inst['name'];
        $oic['type'] = 'group';
        $oic['virtual'] = true;
        $oic['networks'] = array();
        $interfaces[$if] = $oic;
    }

    return $interfaces;
}

function openconnect_xmlrpc_sync()
{
    $result = array();
    $result['id'] = 'openconnectvpn';
    $result['section'] = 'OPNsense.openconnect';
    $result['description'] = gettext('OpenConnect');
    $result['services'] = ['openconnect'];
    return array($result);
}

function openconnect_devices()
{
    $devices = array();
    foreach (openconnect_instances() as $inst) {
        $devices[] = array('pattern' => '^' . $inst['iface'] . '$', 'volatile' => true);
    }
    return $devices;
}
