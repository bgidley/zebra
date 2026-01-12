VERSION 5.00
Begin VB.UserControl ImageCaption 
   Appearance      =   0  'Flat
   BackColor       =   &H80000005&
   BorderStyle     =   1  'Fixed Single
   CanGetFocus     =   0   'False
   ClientHeight    =   1050
   ClientLeft      =   0
   ClientTop       =   0
   ClientWidth     =   4545
   Enabled         =   0   'False
   BeginProperty Font 
      Name            =   "Tahoma"
      Size            =   12
      Charset         =   0
      Weight          =   700
      Underline       =   0   'False
      Italic          =   0   'False
      Strikethrough   =   0   'False
   EndProperty
   ScaleHeight     =   70
   ScaleMode       =   3  'Pixel
   ScaleWidth      =   303
End
Attribute VB_Name = "ImageCaption"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = True
Attribute VB_PredeclaredId = False
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
Private Const mcsglOffset As Single = 8
Private mstrCaption As String
Private moPicture As IPictureDisp

Private Sub UserControl_Paint()
    Call Redraw
End Sub

Private Sub UserControl_Resize()
    Call Redraw
End Sub

Public Sub Setup(Caption As String, Picture As IPictureDisp)
    mstrCaption = Caption
    Set moPicture = Picture
    Call Redraw
End Sub

Public Sub Redraw()
    Static fRecursive As Boolean
    If fRecursive Then Exit Sub
    fRecursive = True
    Height = ScaleY(32 + mcsglOffset * 2, vbPixels, vbTwips)
    Cls
    If Not moPicture Is Nothing Then
        PaintPicture moPicture, mcsglOffset, mcsglOffset, 32, 32
    End If
    
    UserControl.CurrentX = 32 + mcsglOffset * 2
    UserControl.CurrentY = (48 - UserControl.TextHeight(mstrCaption)) / 2
    UserControl.Print mstrCaption
    
    fRecursive = False
End Sub

Public Property Get Enabled() As Boolean
Attribute Enabled.VB_UserMemId = -514
    Enabled = UserControl.Enabled
End Property

Public Property Let Enabled(v As Boolean)
    UserControl.Enabled = v
End Property

Public Property Get Picture() As IPictureDisp
    Set Picture = moPicture
End Property
