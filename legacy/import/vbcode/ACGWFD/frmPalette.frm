VERSION 5.00
Object = "{86CF1D34-0C5F-11D2-A9FC-0000F8754DA1}#2.0#0"; "MSCOMCT2.OCX"
Begin VB.Form frmPalette 
   Caption         =   "Form1"
   ClientHeight    =   3195
   ClientLeft      =   60
   ClientTop       =   345
   ClientWidth     =   4680
   BeginProperty Font 
      Name            =   "Tahoma"
      Size            =   8.25
      Charset         =   0
      Weight          =   400
      Underline       =   0   'False
      Italic          =   0   'False
      Strikethrough   =   0   'False
   EndProperty
   Icon            =   "frmPalette.frx":0000
   LinkTopic       =   "Form1"
   ScaleHeight     =   3195
   ScaleWidth      =   4680
   ShowInTaskbar   =   0   'False
   StartUpPosition =   3  'Windows Default
   Begin MSComCtl2.FlatScrollBar vsc 
      Height          =   1575
      Left            =   3840
      TabIndex        =   1
      Top             =   480
      Width           =   255
      _ExtentX        =   450
      _ExtentY        =   2778
      _Version        =   393216
      Orientation     =   1245184
   End
   Begin VB.PictureBox picScroll 
      Appearance      =   0  'Flat
      BackColor       =   &H80000005&
      BorderStyle     =   0  'None
      ForeColor       =   &H80000008&
      Height          =   1455
      Left            =   720
      ScaleHeight     =   1455
      ScaleWidth      =   1695
      TabIndex        =   0
      Top             =   1080
      Width           =   1695
   End
   Begin ACGWFD.ImageCaption imc 
      DragMode        =   1  'Automatic
      Height          =   720
      Index           =   0
      Left            =   0
      Top             =   0
      Visible         =   0   'False
      Width           =   2655
      _ExtentX        =   4683
      _ExtentY        =   1270
   End
End
Attribute VB_Name = "frmPalette"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Version 2.0 (the "License");
' * you may not use this file except in compliance with the License.
' * You may obtain a copy of the License at
' *
' *    http://www.apache.org/licenses/LICENSE-2.0
' *
' * Unless required by applicable law or agreed to in writing, software
' * distributed under the License is distributed on an "AS IS" BASIS,
' * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
' * See the License for the specific language governing permissions and
' * limitations under the License.
' */
Option Explicit

Private Const mcsglOffset = 64 '/ twips offset between images
Private Const mcstrModule = "frmPalette"

Public Sub AddImage(Caption As String, ID As String, ImageFile As String, ToolTipText As String)
    '/ Add a palette image
    Const cstrFunc = "AddImage"
    On Error GoTo Err_Handler
    Dim ctlImage As ImageCaption
    Dim ctl As VBControlExtender
    
    If imc.UBound = 0 And imc(0).Enabled = False Then
        Set ctlImage = imc(0)
        Set ctl = imc(0)
    Else
        Load imc(imc.UBound + 1)
        Set ctlImage = imc(imc.UBound)
        Set ctl = imc(imc.UBound)
    End If
    ctlImage.Setup Caption, LoadPicture(App.Path & mcstrImagesPath & ImageFile)
    ctl.Tag = ID
    ctl.ToolTipText = ToolTipText
    ctl.Enabled = True
    ctl.Visible = True
    Set ctl.Container = picScroll
    Exit Sub
Err_Handler:
    Select Case reportError(Err, Me, cstrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select
End Sub

Public Sub Redraw()
    '/ redraw the screen
    Const cstrFunc = "Redraw"
    On Error GoTo Err_Handler
    '/ move palette images to fill client area
    Dim sglY As Single
    Dim lngCount As Long
    '# this can be ZERO if the window has become undocked
    If ScaleWidth = 0 Then Exit Sub
    For lngCount = imc.LBound To imc.UBound
        If imc(lngCount).Enabled Then
            imc(lngCount).Move 0, sglY, ScaleWidth
            sglY = sglY + imc(lngCount).Height
        End If
    Next
    
    If sglY > ScaleHeight Then
        picScroll.Move 0, 0, ScaleWidth - vsc.Width, sglY
        vsc.Move ScaleWidth - vsc.Width, 0, vsc.Width, ScaleHeight
        vsc.Max = sglY - ScaleHeight
        vsc.Enabled = True
        vsc.Visible = True
        vsc.Value = 0
        vsc.SmallChange = imc(0).Height
        vsc.LargeChange = imc(0).Height
        For lngCount = imc.LBound To imc.UBound
            If imc(lngCount).Enabled Then
                imc(lngCount).Width = ScaleWidth - vsc.Width
            End If
        Next
    Else
        picScroll.Move 0, 0, ScaleWidth, sglY
        vsc.Visible = False
        vsc.Enabled = False
    End If
    
    
    Exit Sub
Err_Handler:
    Select Case reportError(Err, Me, cstrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select
End Sub

Private Sub Form_Resize()
    Redraw
End Sub

Private Sub vsc_Change()
    picScroll.Top = -vsc.Value
End Sub
