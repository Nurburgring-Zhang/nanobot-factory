/**
 * NModal via ModalForm smoke tests.
 *
 * ModalForm uses NModal which teleports to document.body — assertions therefore
 * look at document.body.innerHTML, not the wrapper element.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ModalForm from '@/components/ModalForm.vue'

interface Form {
  name: string
}

describe('ModalForm', () => {
  beforeEach(() => {
    // Wipe any teleported modals from previous tests.
    if (typeof document !== 'undefined') {
      document.body.innerHTML = ''
    }
  })

  it('renders title prop when shown', async () => {
    const wrapper = mount(ModalForm, {
      attachTo: document.body,
      props: {
        show: true,
        title: 'Create',
        modelValue: { name: '' } as Form,
        submitText: 'Save'
      }
    })
    await new Promise((r) => setTimeout(r, 0))
    expect(document.body.innerHTML).toContain('Create')
    wrapper.unmount()
  })

  it('renders submitText on the primary button when shown', async () => {
    const wrapper = mount(ModalForm, {
      attachTo: document.body,
      props: {
        show: true,
        title: 'Edit',
        modelValue: { name: '' } as Form,
        submitText: 'Apply changes'
      }
    })
    await new Promise((r) => setTimeout(r, 0))
    expect(document.body.innerHTML).toContain('Apply changes')
    wrapper.unmount()
  })

  it('emits cancel when the cancel button is clicked', async () => {
    const wrapper = mount(ModalForm, {
      attachTo: document.body,
      props: {
        show: true,
        title: 'X',
        modelValue: { name: '' } as Form
      }
    })
    await new Promise((r) => setTimeout(r, 0))
    const cancelBtn = document.querySelectorAll('button')
    // Naive UI modal renders the cancel button with the locale string for "Cancel".
    // Our locales use '取消' (zh-CN) since setup resets to that.
    let target: HTMLButtonElement | null = null
    cancelBtn.forEach((b) => {
      if (/Cancel|取消/.test(b.textContent || '')) target = b as HTMLButtonElement
    })
    expect(target).toBeTruthy()
    if (target) {
      target.click()
      // Wait for the @click → emit chain.
      await new Promise((r) => setTimeout(r, 0))
      expect(wrapper.emitted('cancel')).toBeTruthy()
    }
    wrapper.unmount()
  })

  it('renders default form slot when shown', async () => {
    const wrapper = mount(ModalForm, {
      attachTo: document.body,
      props: {
        show: true,
        title: 'T',
        modelValue: { name: '' } as Form
      },
      slots: {
        default: '<input class="probe" />'
      }
    })
    await new Promise((r) => setTimeout(r, 0))
    expect(document.querySelector('.probe')).toBeTruthy()
    wrapper.unmount()
  })
})