#ifndef __GENERIC_IRQ_H
#define __GENERIC_IRQ_H

#include <stdint.h> // uint32_t

typedef unsigned long irqstatus_t;

void irq_disable(void);
void irq_enable(void);
irqstatus_t irq_save(void);
void irq_restore(irqstatus_t flag);
void irq_wait(void);
void irq_poll(void);
// Boards that dispatch timers from irq_wait() (CONFIG_HAVE_IRQ_WAIT_TIMERS):
// return, and reset, the clock ticks spent on that since the last call
uint32_t irq_wait_timer_ticks(void);

#endif // irq.h
