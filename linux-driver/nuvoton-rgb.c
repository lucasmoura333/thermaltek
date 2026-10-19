/*
 * Nuvoton RGB Controller Driver
 * 
 * Driver for Nuvoton 0416:8001 HID RGB Controller
 * (Thermaltake Assassin 120 Digital)
 *
 * Copyright (C) 2025
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/hid.h>
#include <linux/mutex.h>
#include <linux/slab.h>

#define DRIVER_NAME "nuvoton-rgb"
#define DRIVER_DESC "Nuvoton RGB Controller Driver"
#define DRIVER_VERSION "1.0"

/* Device IDs */
#define USB_VENDOR_ID_NUVOTON   0x0416
#define USB_DEVICE_ID_RGB_CTRL  0x8001

/* HID Report specifications */
#define REPORT_SIZE 64
#define REPORT_ID_RGB 0x00

/* Device private data */
struct nuvoton_rgb_device {
    struct hid_device *hdev;
    struct mutex lock;
    u8 red;
    u8 green;
    u8 blue;
    bool initialized;
};

/*
 * Send HID output report to device
 * This function is thread-safe via mutex
 */
static int nuvoton_send_report(struct nuvoton_rgb_device *drvdata, 
                                const u8 *data, size_t len)
{
    int ret;
    u8 *buf;

    if (!drvdata || !data || len == 0 || len > REPORT_SIZE)
        return -EINVAL;

    buf = kzalloc(len + 1, GFP_KERNEL);
    if (!buf)
        return -ENOMEM;

    buf[0] = REPORT_ID_RGB;
    memcpy(buf + 1, data, len);

    mutex_lock(&drvdata->lock);
    
    ret = hid_hw_output_report(drvdata->hdev, buf, len + 1);
    if (ret < 0) {
        hid_err(drvdata->hdev, "Failed to send HID report: %d\n", ret);
    } else {
        hid_dbg(drvdata->hdev, "Sent %d bytes to device\n", ret);
    }
    
    mutex_unlock(&drvdata->lock);
    
    kfree(buf);
    return ret;
}

/*
 * Attempt to set RGB color
 * Note: Protocol is still being discovered, this implements
 * common patterns that may or may not work
 */
static int nuvoton_set_color(struct nuvoton_rgb_device *drvdata,
                              u8 red, u8 green, u8 blue)
{
    u8 buf[REPORT_SIZE];
    int ret;

    memset(buf, 0, REPORT_SIZE);
    
    /* Try multiple protocol patterns */
    
    /* Pattern 1: Simple RGB at start */
    buf[0] = 0x01;  /* Command ID */
    buf[1] = red;
    buf[2] = green;
    buf[3] = blue;
    
    ret = nuvoton_send_report(drvdata, buf, REPORT_SIZE);
    if (ret < 0)
        return ret;

    /* Pattern 2: With magic header */
    memset(buf, 0, REPORT_SIZE);
    buf[0] = 0x5A;  /* Common magic byte */
    buf[1] = 0x01;  /* Command: Set Color */
    buf[2] = red;
    buf[3] = green;
    buf[4] = blue;
    
    ret = nuvoton_send_report(drvdata, buf, REPORT_SIZE);
    if (ret < 0)
        return ret;

    /* Store current values */
    drvdata->red = red;
    drvdata->green = green;
    drvdata->blue = blue;

    hid_info(drvdata->hdev, "RGB color set to: R=%d G=%d B=%d\n", 
             red, green, blue);

    return 0;
}

/* Sysfs attributes */
static ssize_t red_show(struct device *dev, struct device_attribute *attr,
                        char *buf)
{
    struct nuvoton_rgb_device *drvdata = dev_get_drvdata(dev);
    return sprintf(buf, "%d\n", drvdata->red);
}

static ssize_t red_store(struct device *dev, struct device_attribute *attr,
                         const char *buf, size_t count)
{
    struct nuvoton_rgb_device *drvdata = dev_get_drvdata(dev);
    u8 value;
    int ret;

    ret = kstrtou8(buf, 10, &value);
    if (ret)
        return ret;

    ret = nuvoton_set_color(drvdata, value, drvdata->green, drvdata->blue);
    if (ret < 0)
        return ret;

    return count;
}

static ssize_t green_show(struct device *dev, struct device_attribute *attr,
                          char *buf)
{
    struct nuvoton_rgb_device *drvdata = dev_get_drvdata(dev);
    return sprintf(buf, "%d\n", drvdata->green);
}

static ssize_t green_store(struct device *dev, struct device_attribute *attr,
                           const char *buf, size_t count)
{
    struct nuvoton_rgb_device *drvdata = dev_get_drvdata(dev);
    u8 value;
    int ret;

    ret = kstrtou8(buf, 10, &value);
    if (ret)
        return ret;

    ret = nuvoton_set_color(drvdata, drvdata->red, value, drvdata->blue);
    if (ret < 0)
        return ret;

    return count;
}

static ssize_t blue_show(struct device *dev, struct device_attribute *attr,
                         char *buf)
{
    struct nuvoton_rgb_device *drvdata = dev_get_drvdata(dev);
    return sprintf(buf, "%d\n", drvdata->blue);
}

static ssize_t blue_store(struct device *dev, struct device_attribute *attr,
                          const char *buf, size_t count)
{
    struct nuvoton_rgb_device *drvdata = dev_get_drvdata(dev);
    u8 value;
    int ret;

    ret = kstrtou8(buf, 10, &value);
    if (ret)
        return ret;

    ret = nuvoton_set_color(drvdata, drvdata->red, drvdata->green, value);
    if (ret < 0)
        return ret;

    return count;
}

static ssize_t color_store(struct device *dev, struct device_attribute *attr,
                           const char *buf, size_t count)
{
    struct nuvoton_rgb_device *drvdata = dev_get_drvdata(dev);
    u8 red, green, blue;
    int ret;

    ret = sscanf(buf, "%hhu %hhu %hhu", &red, &green, &blue);
    if (ret != 3)
        return -EINVAL;

    ret = nuvoton_set_color(drvdata, red, green, blue);
    if (ret < 0)
        return ret;

    return count;
}

static ssize_t color_show(struct device *dev, struct device_attribute *attr,
                          char *buf)
{
    struct nuvoton_rgb_device *drvdata = dev_get_drvdata(dev);
    return sprintf(buf, "%d %d %d\n", drvdata->red, drvdata->green, 
                   drvdata->blue);
}

/* Device attributes */
static DEVICE_ATTR_RW(red);
static DEVICE_ATTR_RW(green);
static DEVICE_ATTR_RW(blue);
static DEVICE_ATTR_RW(color);

static struct attribute *nuvoton_rgb_attrs[] = {
    &dev_attr_red.attr,
    &dev_attr_green.attr,
    &dev_attr_blue.attr,
    &dev_attr_color.attr,
    NULL,
};

static const struct attribute_group nuvoton_rgb_attr_group = {
    .attrs = nuvoton_rgb_attrs,
};

/* HID driver callbacks */
static int nuvoton_rgb_probe(struct hid_device *hdev,
                             const struct hid_device_id *id)
{
    struct nuvoton_rgb_device *drvdata;
    int ret;

    hid_info(hdev, "Nuvoton RGB Controller detected\n");

    drvdata = devm_kzalloc(&hdev->dev, sizeof(*drvdata), GFP_KERNEL);
    if (!drvdata)
        return -ENOMEM;

    drvdata->hdev = hdev;
    mutex_init(&drvdata->lock);
    drvdata->initialized = false;

    hid_set_drvdata(hdev, drvdata);

    ret = hid_parse(hdev);
    if (ret) {
        hid_err(hdev, "Parse failed\n");
        return ret;
    }

    ret = hid_hw_start(hdev, HID_CONNECT_DEFAULT);
    if (ret) {
        hid_err(hdev, "HW start failed\n");
        return ret;
    }

    ret = hid_hw_open(hdev);
    if (ret) {
        hid_err(hdev, "HW open failed\n");
        goto err_stop;
    }

    /* Create sysfs attributes */
    ret = sysfs_create_group(&hdev->dev.kobj, &nuvoton_rgb_attr_group);
    if (ret) {
        hid_err(hdev, "Failed to create sysfs attributes\n");
        goto err_close;
    }

    /* Initialize with white color */
    drvdata->red = 255;
    drvdata->green = 255;
    drvdata->blue = 255;
    
    nuvoton_set_color(drvdata, 255, 255, 255);
    drvdata->initialized = true;

    hid_info(hdev, "Nuvoton RGB Controller initialized successfully\n");
    hid_info(hdev, "Sysfs interface: /sys/bus/hid/devices/%s/\n", 
             dev_name(&hdev->dev));

    return 0;

err_close:
    hid_hw_close(hdev);
err_stop:
    hid_hw_stop(hdev);
    return ret;
}

static void nuvoton_rgb_remove(struct hid_device *hdev)
{
    struct nuvoton_rgb_device *drvdata = hid_get_drvdata(hdev);

    hid_info(hdev, "Removing Nuvoton RGB Controller\n");

    sysfs_remove_group(&hdev->dev.kobj, &nuvoton_rgb_attr_group);
    
    hid_hw_close(hdev);
    hid_hw_stop(hdev);

    mutex_destroy(&drvdata->lock);
}

/* Device ID table */
static const struct hid_device_id nuvoton_rgb_devices[] = {
    { HID_USB_DEVICE(USB_VENDOR_ID_NUVOTON, USB_DEVICE_ID_RGB_CTRL) },
    { }
};
MODULE_DEVICE_TABLE(hid, nuvoton_rgb_devices);

/* HID driver structure */
static struct hid_driver nuvoton_rgb_driver = {
    .name = DRIVER_NAME,
    .id_table = nuvoton_rgb_devices,
    .probe = nuvoton_rgb_probe,
    .remove = nuvoton_rgb_remove,
};

module_hid_driver(nuvoton_rgb_driver);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Custom Linux Driver");
MODULE_DESCRIPTION(DRIVER_DESC);
MODULE_VERSION(DRIVER_VERSION);
